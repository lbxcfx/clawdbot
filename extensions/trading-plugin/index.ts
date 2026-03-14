import type { AnyAgentTool, OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { createTradingAgentTool } from "./src/tool.js";

const plugin = {
  id: "trading-plugin",
  name: "Trading Plugin",
  description: "OpenClaw 的 trading-agent 运行时工具封装",
  configSchema: emptyPluginConfigSchema(),
  register(api: OpenClawPluginApi) {
    api.registerTool(createTradingAgentTool(api) as unknown as AnyAgentTool);
  },
};

export default plugin;
