import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { Type } from "@sinclair/typebox";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk";

const execFileAsync = promisify(execFile);

const ACTIONS = [
  "sync_daily",
  "sync_status",
  "strategy_daily_report",
  "top_movers",
  "etf_detail",
  "batch_signal_150ma",
] as const;

type TradingAction = (typeof ACTIONS)[number];

type TradingPluginConfig = {
  pythonBin?: string;
  scriptPath?: string;
  dbPath?: string;
};

type ToolParams = {
  action: TradingAction;
  tradeDate?: string;
  symbol?: string;
  start?: string;
  end?: string;
  top?: number;
  recentBars?: number;
  db?: string;
};

function stringEnum<T extends readonly string[]>(
  values: T,
  options: { description?: string } = {},
) {
  return Type.Unsafe<T[number]>({
    type: "string",
    enum: [...values],
    ...options,
  });
}

export const TradingAgentToolSchema = Type.Object(
  {
    action: stringEnum(ACTIONS, {
      description: `Action to perform: ${ACTIONS.join(", ")}`,
    }),
    tradeDate: Type.Optional(Type.String({ description: "Target trade date in YYYY-MM-DD format." })),
    symbol: Type.Optional(Type.String({ description: "ETF symbol for symbol-specific queries." })),
    start: Type.Optional(Type.String({ description: "Start date in YYYY-MM-DD format." })),
    end: Type.Optional(Type.String({ description: "End date in YYYY-MM-DD format." })),
    top: Type.Optional(Type.Number({ description: "Top-N rows for top_movers." })),
    recentBars: Type.Optional(Type.Number({ description: "Recent K-line count for etf_detail." })),
    db: Type.Optional(Type.String({ description: "Optional DB path override." })),
  },
  { additionalProperties: false },
);

function json(payload: unknown) {
  return {
    content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
    details: payload,
  };
}

function requireString(value: string | undefined, field: string): string {
  const trimmed = value?.trim();
  if (!trimmed) {
    throw new Error(`${field} is required`);
  }
  return trimmed;
}

function resolveTradingPaths(api: OpenClawPluginApi, params: ToolParams) {
  const pluginCfg = (api.pluginConfig ?? {}) as TradingPluginConfig;
  return {
    pythonBin: pluginCfg.pythonBin?.trim() || (process.platform === "win32" ? "python" : "python3"),
    scriptPath: api.resolvePath(
      pluginCfg.scriptPath?.trim() || "../../stock-agent/local-prototype/scripts/stock_agent.py",
    ),
    dbPath: api.resolvePath(
      params.db?.trim() || pluginCfg.dbPath?.trim() || "../../stock-agent/local-prototype/data/industry.db",
    ),
  };
}

function buildCommandArgs(params: ToolParams, dbPath: string): string[] {
  switch (params.action) {
    case "sync_daily": {
      const args = ["sync-daily", "--db", dbPath];
      if (params.tradeDate) {
        args.push("--trade-date", params.tradeDate);
      }
      return args;
    }
    case "sync_status":
      return ["sync-status", "--db", dbPath];
    case "strategy_daily_report": {
      const args = ["strategy-daily-report", "--db", dbPath];
      if (params.tradeDate) {
        args.push("--trade-date", params.tradeDate);
      }
      return args;
    }
    case "top_movers": {
      const args = ["top-movers", "--db", dbPath];
      if (params.tradeDate) {
        args.push("--trade-date", params.tradeDate);
      }
      if (typeof params.top === "number" && Number.isFinite(params.top)) {
        args.push("--top", String(Math.trunc(params.top)));
      }
      return args;
    }
    case "etf_detail": {
      const args = ["etf-detail", "--db", dbPath, "--symbol", requireString(params.symbol, "symbol")];
      if (params.start) {
        args.push("--start", params.start);
      }
      if (params.end) {
        args.push("--end", params.end);
      }
      if (typeof params.recentBars === "number" && Number.isFinite(params.recentBars)) {
        args.push("--recent-bars", String(Math.trunc(params.recentBars)));
      }
      return args;
    }
    case "batch_signal_150ma": {
      const args = ["batch-signal-150ma", "--db", dbPath];
      if (params.tradeDate) {
        args.push("--trade-date", params.tradeDate);
      }
      return args;
    }
    default: {
      params.action satisfies never;
      throw new Error(`Unsupported action: ${String(params.action)}`);
    }
  }
}

export function createTradingAgentTool(api: OpenClawPluginApi) {
  return {
    name: "trading_agent",
    label: "Trading Agent",
    description:
      "Access the local stock-agent prototype for daily sync, strategy daily report, top movers, ETF detail, and batch signal queries.",
    parameters: TradingAgentToolSchema,
    async execute(_id: string, rawParams: Record<string, unknown>) {
      const params = rawParams as unknown as ToolParams;
      try {
        const { pythonBin, scriptPath, dbPath } = resolveTradingPaths(api, params);
        const args = [scriptPath, ...buildCommandArgs(params, dbPath)];
        const { stdout, stderr } = await execFileAsync(pythonBin, args, {
          cwd: api.resolvePath("../../"),
          encoding: "utf8",
          maxBuffer: 10 * 1024 * 1024,
        });
        const text = stdout.trim();
        if (!text) {
          throw new Error(stderr.trim() || "Trading tool returned empty output");
        }
        const parsed = JSON.parse(text) as unknown;
        return json(parsed);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : `Trading tool execution failed: ${String(error)}`;
        return json({
          kind: "trading_tool_error",
          action: params.action,
          error: message,
        });
      }
    },
  };
}
