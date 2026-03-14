import { beforeEach, describe, expect, it, vi } from "vitest";

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

import { buildCommandArgs, createTradingAgentTool } from "./tool.js";

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

function fakeConfiguredApi() {
  return fakeApi({
    resolvePath: (p: string) => p,
    pluginConfig: {
      pythonBin: "python3",
      scriptPath: "/workspace/stock-agent/trading-agent/scripts/stock_agent.py",
      dbPath: "/workspace/.openclaw/workspace-trading-agent/data/industry.db",
      bundledDbPath: "/workspace/stock-agent/trading-agent/data/industry.db",
      seedCsvPath: "/workspace/stock-agent/trading-agent/data/industry-etf-candidates.csv",
    },
  });
}

describe("trading_agent tool", () => {
  beforeEach(() => {
    execFileState.execFile.mockReset();
  });

  it("runs bootstrap before strategy_daily_report", async () => {
    let callIndex = 0;
    execFileState.execFile.mockImplementation(
      (
        _file: string,
        _args: string[],
        _options: Record<string, unknown>,
        callback: (error: Error | null, stdout: string, stderr: string) => void,
      ) => {
        callIndex += 1;
        if (callIndex === 1) {
          callback(
            null,
            JSON.stringify({ kind: "bootstrap_db", seeded: false, universe_symbols: 2 }),
            "",
          );
        } else {
          callback(null, JSON.stringify({ kind: "strategy_daily_report", sell_count: 4 }), "");
        }
        return {} as never;
      },
    );

    expect(
      buildCommandArgs(
        {
          action: "strategy_daily_report",
          tradeDate: "2026-03-12",
        },
        "/workspace/.openclaw/workspace-trading/data/industry.db",
      ),
    ).toEqual([
      "strategy-daily-report",
      "--db",
      "/workspace/.openclaw/workspace-trading/data/industry.db",
      "--trade-date",
      "2026-03-12",
    ]);

    const tool = createTradingAgentTool(
      fakeApi({
        resolvePath: (p: string) => p,
        pluginConfig: {
          pythonBin: "python3",
          scriptPath: "/workspace/stock-agent/trading-agent/scripts/stock_agent.py",
          dbPath: "/workspace/.openclaw/workspace-trading/data/industry.db",
          bundledDbPath: "/workspace/stock-agent/trading-agent/data/industry.db",
          seedCsvPath: "/workspace/stock-agent/trading-agent/data/industry-etf-candidates.csv",
        },
      }) as never,
    );

    await tool.execute("tool-1", {
      action: "strategy_daily_report",
      tradeDate: "2026-03-12",
    });

    expect(execFileState.execFile).toHaveBeenCalled();
    const firstCall = execFileState.execFile.mock.calls[0];
    expect(firstCall?.[0]).toBe("python3");
    expect(firstCall?.[1]).toEqual([
      "/workspace/stock-agent/trading-agent/scripts/stock_agent.py",
      "bootstrap-db",
      "--db",
      "/workspace/.openclaw/workspace-trading/data/industry.db",
      "--csv",
      "/workspace/stock-agent/trading-agent/data/industry-etf-candidates.csv",
    ]);
  });

  it("requires symbol for etf_detail", async () => {
    const tool = createTradingAgentTool(fakeConfiguredApi() as never);

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

  it("requires symbol for technical_indicators", async () => {
    const tool = createTradingAgentTool(fakeConfiguredApi() as never);

    const result = await tool.execute("tool-tech-1", {
      action: "technical_indicators",
    });

    expect(result).toMatchObject({
      details: {
        kind: "trading_tool_error",
        action: "technical_indicators",
        error: expect.stringContaining("symbol is required"),
      },
    });
  });

  it("builds technical_analysis args with include-series", () => {
    expect(
      buildCommandArgs(
        {
          action: "technical_analysis",
          symbol: "159611",
          end: "2026-03-12",
          recentBars: 15,
          includeSeries: true,
        },
        "../../stock-agent/trading-agent/data/industry.db",
      ),
    ).toEqual([
      "technical-analysis",
      "--db",
      "../../stock-agent/trading-agent/data/industry.db",
      "--symbol",
      "159611",
      "--end",
      "2026-03-12",
      "--recent-bars",
      "15",
      "--include-series",
    ]);
  });

  it("builds latest_price args", () => {
    expect(
      buildCommandArgs(
        {
          action: "latest_price",
          symbol: "159611",
        },
        "../../stock-agent/trading-agent/data/industry.db",
      ),
    ).toEqual([
      "latest-price",
      "--db",
      "../../stock-agent/trading-agent/data/industry.db",
      "--symbol",
      "159611",
    ]);
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

    const tool = createTradingAgentTool(fakeConfiguredApi() as never);
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

  it("builds search_etf args and runs bootstrap first", async () => {
    let callIndex = 0;
    execFileState.execFile.mockImplementation(
      (
        _file: string,
        _args: string[],
        _options: Record<string, unknown>,
        callback: (error: Error | null, stdout: string, stderr: string) => void,
      ) => {
        callIndex += 1;
        if (callIndex === 1) {
          callback(
            null,
            JSON.stringify({ kind: "bootstrap_db", seeded: false, universe_symbols: 2 }),
            "",
          );
        } else {
          callback(
            null,
            JSON.stringify({
              kind: "etf_search",
              query: "电池ETF",
              match_count: 2,
              resolved_symbol: null,
            }),
            "",
          );
        }
        return {} as never;
      },
    );

    expect(
      buildCommandArgs(
        {
          action: "search_etf",
          query: "电池ETF",
          limit: 5,
        },
        "../../stock-agent/trading-agent/data/industry.db",
      ),
    ).toEqual([
      "search-etf",
      "--db",
      "../../stock-agent/trading-agent/data/industry.db",
      "--query",
      "电池ETF",
      "--limit",
      "5",
    ]);

    const tool = createTradingAgentTool(fakeApi() as never);
    await tool.execute("tool-4", {
      action: "search_etf",
      query: "电池ETF",
      limit: 5,
    });

    const firstCall = execFileState.execFile.mock.calls[0];
    expect(firstCall?.[1]).toEqual([
      "../../stock-agent/trading-agent/scripts/stock_agent.py",
      "bootstrap-db",
      "--db",
      "../../stock-agent/trading-agent/data/industry.db",
      "--csv",
      "../../stock-agent/trading-agent/data/industry-etf-candidates.csv",
    ]);
  });
});
