import { describe, expect, it, vi, beforeEach } from "vitest";

const execFileState = vi.hoisted(() => ({
  execFile: vi.fn(),
}));

vi.mock("node:child_process", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:child_process")>();
  return {
    ...actual,
    execFile: execFileState.execFile,
  };
});

import { createTradingAgentTool } from "./tool.js";

function fakeApi(overrides: Record<string, unknown> = {}) {
  return {
    id: "trading-plugin",
    name: "trading-plugin",
    source: "test",
    config: {},
    pluginConfig: {},
    runtime: { version: "test" },
    logger: { info() {}, warn() {}, error() {}, debug() {} },
    registerTool() {},
    registerChannel() {},
    registerGatewayMethod() {},
    registerCli() {},
    registerService() {},
    registerProvider() {},
    registerHook() {},
    registerHttpRoute() {},
    registerCommand() {},
    registerContextEngine() {},
    on() {},
    resolvePath: (p: string) => p,
    ...overrides,
  };
}

describe("trading_agent tool", () => {
  beforeEach(() => {
    execFileState.execFile.mockReset();
  });

  it("runs strategy_daily_report with configured python and paths", async () => {
    execFileState.execFile.mockImplementation(
      (
        _file: string,
        _args: string[],
        _options: Record<string, unknown>,
        callback: (error: Error | null, stdout: string, stderr: string) => void,
      ) => {
        callback(null, JSON.stringify({ kind: "strategy_daily_report", sell_count: 4 }), "");
        return {} as never;
      },
    );

    const tool = createTradingAgentTool(
      fakeApi({
        pluginConfig: {
          pythonBin: "python3",
          scriptPath: "/workspace/stock-agent/local-prototype/scripts/stock_agent.py",
          dbPath: "/workspace/.openclaw/workspace-trading/data/industry.db",
        },
      }) as never,
    );

    await tool.execute("tool-1", {
      action: "strategy_daily_report",
      tradeDate: "2026-03-12",
    });

    expect(execFileState.execFile).toHaveBeenCalledTimes(1);
    expect(execFileState.execFile.mock.calls[0]?.[0]).toBe("python3");
    expect(execFileState.execFile.mock.calls[0]?.[1]).toEqual([
      "/workspace/stock-agent/local-prototype/scripts/stock_agent.py",
      "strategy-daily-report",
      "--db",
      "/workspace/.openclaw/workspace-trading/data/industry.db",
      "--trade-date",
      "2026-03-12",
    ]);
  });

  it("requires symbol for etf_detail", async () => {
    const tool = createTradingAgentTool(fakeApi() as never);

    const result = await tool.execute("tool-2", {
      action: "etf_detail",
    });

    expect(result).toMatchObject({
      details: {
        kind: "trading_tool_error",
        action: "etf_detail",
        error: expect.stringContaining("symbol is required"),
      },
    });
  });

  it("returns trading_tool_error on invalid json output", async () => {
    execFileState.execFile.mockImplementation(
      (
        _file: string,
        _args: string[],
        _options: Record<string, unknown>,
        callback: (error: Error | null, stdout: string, stderr: string) => void,
      ) => {
        callback(null, "not-json", "");
        return {} as never;
      },
    );

    const tool = createTradingAgentTool(fakeApi() as never);
    const result = await tool.execute("tool-3", {
      action: "sync_status",
    });

    expect(result).toMatchObject({
      details: {
        kind: "trading_tool_error",
        action: "sync_status",
      },
    });
  });
});
