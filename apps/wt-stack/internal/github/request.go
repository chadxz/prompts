package github

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const (
	maxResponseBytes = 10 << 20
	maxReadAttempts  = 3
	maxRetryDelay    = 60 * time.Second
)

var retryableStatusCodes = map[int]struct{}{
	http.StatusTooManyRequests:    {},
	http.StatusBadGateway:         {},
	http.StatusServiceUnavailable: {},
	http.StatusGatewayTimeout:     {},
}

type apiResponse struct {
	StatusCode int
	Header     http.Header
	Body       []byte
}

// APIError describes a non-successful response from GitHub.
type APIError struct {
	StatusCode int
	Path       string
	Message    string
	Details    []string
}

// Error formats the GitHub response without exposing authentication details.
func (e *APIError) Error() string {
	message := e.Message
	if len(e.Details) > 0 {
		if message != "" {
			message += ": "
		}
		message += strings.Join(e.Details, "; ")
	}
	if message == "" {
		return fmt.Sprintf("GitHub API returned HTTP %d for %s", e.StatusCode, e.Path)
	}
	return fmt.Sprintf(
		"GitHub API returned HTTP %d for %s: %s",
		e.StatusCode,
		e.Path,
		message,
	)
}

func (c *Client) request(
	ctx context.Context,
	repository Repository,
	method string,
	path string,
	requestBody any,
	responseBody any,
) (http.Header, error) {
	if err := validateAPIHost(repository); err != nil {
		return nil, err
	}
	encodedRequest, err := encodeRequest(requestBody)
	if err != nil {
		return nil, err
	}

	authRetried := false
	attempts := 1
	if method == http.MethodGet || method == http.MethodPatch {
		attempts = maxReadAttempts
	}
	for attempt := 0; attempt < attempts; attempt++ {
		token, tokenErr := c.token(ctx, repository.Host)
		if tokenErr != nil {
			return nil, tokenErr
		}
		response, requestErr := c.doRequest(
			ctx,
			repository,
			method,
			path,
			encodedRequest,
			token,
		)
		if requestErr != nil {
			return nil, requestErr
		}
		if response.StatusCode == http.StatusUnauthorized && !authRetried {
			authRetried = true
			c.invalidateToken(repository.Host)
			attempt--
			continue
		}
		if retryableResponse(response) && attempt+1 < attempts {
			if err := waitForRetry(ctx, attempt, response.Header); err != nil {
				return nil, err
			}
			continue
		}
		if response.StatusCode < http.StatusOK ||
			response.StatusCode >= http.StatusMultipleChoices {
			return nil, decodeAPIError(response.StatusCode, path, response.Body)
		}
		if responseBody != nil && len(response.Body) > 0 {
			if err := json.Unmarshal(response.Body, responseBody); err != nil {
				return nil, fmt.Errorf("decoding GitHub API response: %w", err)
			}
		}
		return response.Header, nil
	}
	return nil, errors.New("GitHub API request exhausted retries")
}

func encodeRequest(requestBody any) ([]byte, error) {
	if requestBody == nil {
		return nil, nil
	}
	encoded, err := json.Marshal(requestBody)
	if err != nil {
		return nil, fmt.Errorf("encoding GitHub API request: %w", err)
	}
	return encoded, nil
}

func (c *Client) doRequest(
	ctx context.Context,
	repository Repository,
	method string,
	path string,
	body []byte,
	token string,
) (apiResponse, error) {
	endpoint := strings.TrimRight(repository.APIURL, "/") + "/" +
		strings.TrimLeft(path, "/")
	request, err := http.NewRequestWithContext(
		ctx,
		method,
		endpoint,
		bytes.NewReader(body),
	)
	if err != nil {
		return apiResponse{}, fmt.Errorf("creating GitHub API request: %w", err)
	}
	request.Header.Set("Accept", "application/vnd.github+json")
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("User-Agent", "wt-stack")

	response, err := c.httpClient.Do(request)
	if err != nil {
		return apiResponse{}, fmt.Errorf("calling GitHub API: %w", err)
	}
	defer func() {
		_ = response.Body.Close()
	}()

	data, err := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes+1))
	if err != nil {
		return apiResponse{}, fmt.Errorf("reading GitHub API response: %w", err)
	}
	if len(data) > maxResponseBytes {
		return apiResponse{}, fmt.Errorf(
			"reading GitHub API response: body exceeds %d bytes",
			maxResponseBytes,
		)
	}
	return apiResponse{
		StatusCode: response.StatusCode,
		Header:     response.Header.Clone(),
		Body:       data,
	}, nil
}

func validateAPIHost(repository Repository) error {
	actual, err := url.Parse(repository.APIURL)
	if err != nil {
		return fmt.Errorf("parsing GitHub API URL: %w", err)
	}
	expected, err := url.Parse(apiURLForHost(repository.Host))
	if err != nil {
		return fmt.Errorf("parsing expected GitHub API URL: %w", err)
	}
	if actual.Hostname() == "" ||
		!strings.EqualFold(actual.Hostname(), expected.Hostname()) {
		return fmt.Errorf(
			"refusing to send GitHub authentication for %s to API host %q",
			repository.Host,
			actual.Hostname(),
		)
	}
	if actual.Scheme != expected.Scheme {
		address := net.ParseIP(actual.Hostname())
		if actual.Scheme != "http" ||
			address == nil ||
			!address.IsLoopback() {
			return fmt.Errorf(
				"refusing to send GitHub authentication over %q for %s",
				actual.Scheme,
				repository.Host,
			)
		}
	}
	return nil
}

func retryableResponse(response apiResponse) bool {
	if _, retryable := retryableStatusCodes[response.StatusCode]; retryable {
		return true
	}
	if response.StatusCode != http.StatusForbidden {
		return false
	}
	return response.Header.Get("Retry-After") != "" ||
		response.Header.Get("X-RateLimit-Remaining") == "0"
}

func decodeAPIError(
	statusCode int,
	path string,
	response []byte,
) error {
	var body struct {
		Message string            `json:"message"`
		Errors  []json.RawMessage `json:"errors"`
	}
	if err := json.Unmarshal(response, &body); err != nil {
		body.Message = strings.TrimSpace(string(response))
	}
	details := make([]string, 0, len(body.Errors))
	for _, raw := range body.Errors {
		var message string
		if err := json.Unmarshal(raw, &message); err == nil {
			details = append(details, message)
			continue
		}
		var item struct {
			Resource string `json:"resource"`
			Field    string `json:"field"`
			Code     string `json:"code"`
			Message  string `json:"message"`
		}
		if err := json.Unmarshal(raw, &item); err != nil {
			continue
		}
		switch {
		case item.Message != "":
			details = append(details, item.Message)
		case item.Resource != "" || item.Field != "" || item.Code != "":
			details = append(
				details,
				strings.TrimSpace(
					item.Resource+"."+item.Field+" "+item.Code,
				),
			)
		}
	}
	return &APIError{
		StatusCode: statusCode,
		Path:       path,
		Message:    body.Message,
		Details:    details,
	}
}

func waitForRetry(
	ctx context.Context,
	attempt int,
	headers http.Header,
) error {
	delay := retryDelay(time.Now(), attempt, headers)
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return fmt.Errorf("waiting to retry GitHub API request: %w", ctx.Err())
	case <-timer.C:
		return nil
	}
}

func retryDelay(
	now time.Time,
	attempt int,
	headers http.Header,
) time.Duration {
	delay := time.Duration(attempt+1) * 250 * time.Millisecond
	if retryAfter := headers.Get("Retry-After"); retryAfter != "" {
		if seconds, err := strconv.Atoi(retryAfter); err == nil {
			delay = time.Duration(seconds) * time.Second
		} else if when, parseErr := http.ParseTime(retryAfter); parseErr == nil {
			delay = when.Sub(now)
		}
	} else if reset := headers.Get("X-RateLimit-Reset"); reset != "" {
		if timestamp, err := strconv.ParseInt(reset, 10, 64); err == nil {
			delay = time.Unix(timestamp, 0).Sub(now)
		}
	}
	if delay < 0 {
		return 0
	}
	if delay > maxRetryDelay {
		return maxRetryDelay
	}
	return delay
}
