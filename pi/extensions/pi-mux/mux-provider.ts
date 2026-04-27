import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export type MuxProviderControls = {
  connect: string;
  disconnect: string;
  status: string;
};

export type MuxProviderConfig = {
  provider?: string;
  commandName?: string;
  controls?: Partial<MuxProviderControls>;
};

export type MuxProviderFactory =
  | ((pi: ExtensionAPI) => void | Promise<void>)
  | {
      default: (pi: ExtensionAPI) => void | Promise<void>;
    };

export function defineMuxProvider(config: MuxProviderConfig = {}): MuxProviderConfig {
  return config;
}
