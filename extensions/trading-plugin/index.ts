import type { AnyAgentTool, OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { createTradingAgentTool } from "./src/tool.js";

const plugin = {
  id: "trading-plugin",
  name: "Trading Plugin",
  description: "OpenClaw tool wrapper for the local stock-agent prototype",
  configSchema: emptyPluginConfigSchema(),
  register(api: OpenClawPluginApi) {
    api.registerTool(createTradingAgentTool(api) as unknown as AnyAgentTool);
  },
};

export default plugin;
