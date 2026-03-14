import { describe, expect, it, vi } from "vitest";
import plugin from "./index.js";

describe("trading-plugin registration", () => {
  it("registers the trading_agent tool", () => {
    const registerTool = vi.fn();

    plugin.register?.({
      id: "trading-plugin",
      name: "Trading Plugin",
      description: "Trading Plugin",
      source: "test",
      config: {},
      pluginConfig: {},
      runtime: {} as never,
      logger: {
        info() {},
        warn() {},
        error() {},
        debug() {},
      },
      registerTool,
      registerHook() {},
      registerHttpRoute() {},
      registerChannel() {},
      registerGatewayMethod() {},
      registerCli() {},
      registerService() {},
      registerProvider() {},
      registerCommand() {},
      registerContextEngine() {},
      resolvePath(input: string) {
        return input;
      },
      on() {},
    });

    expect(registerTool).toHaveBeenCalledTimes(1);
    expect(registerTool.mock.calls[0]?.[0]).toMatchObject({
      name: "trading_agent",
      label: "Trading Agent",
    });
  });
});
