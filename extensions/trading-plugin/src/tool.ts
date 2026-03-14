import { execFile } from "node:child_process";
import { copyFile, mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { Type } from "@sinclair/typebox";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk";

const execFileAsync = promisify(execFile);

const ACTIONS = [
  "sync_daily",
  "sync_status",
  "strategy_daily_report",
  "top_movers",
  "search_etf",
  "latest_price",
  "etf_detail",
  "technical_indicators",
  "technical_analysis",
  "batch_signal_150ma",
] as const;

type TradingAction = (typeof ACTIONS)[number];

type TradingPluginConfig = {
  pythonBin?: string;
  scriptPath?: string;
  dbPath?: string;
  bundledDbPath?: string;
  seedCsvPath?: string;
};

type ToolParams = {
  action: TradingAction;
  tradeDate?: string;
  query?: string;
  symbol?: string;
  start?: string;
  end?: string;
  top?: number;
  limit?: number;
  recentBars?: number;
  includeSeries?: boolean;
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
      description: `要执行的动作：${ACTIONS.join(", ")}`,
    }),
    tradeDate: Type.Optional(Type.String({ description: "目标交易日，格式为 YYYY-MM-DD。" })),
    query: Type.Optional(Type.String({ description: "ETF 检索文本、代码或板块关键词。" })),
    symbol: Type.Optional(Type.String({ description: "按具体标的查询时使用的 ETF 代码。" })),
    start: Type.Optional(Type.String({ description: "开始日期，格式为 YYYY-MM-DD。" })),
    end: Type.Optional(Type.String({ description: "结束日期，格式为 YYYY-MM-DD。" })),
    top: Type.Optional(Type.Number({ description: "top_movers 返回的前 N 条记录。" })),
    limit: Type.Optional(Type.Number({ description: "search_etf 返回的最大记录数。" })),
    recentBars: Type.Optional(Type.Number({ description: "etf_detail 返回的最近 K 线数量。" })),
    includeSeries: Type.Optional(Type.Boolean({ description: "是否返回最近若干条技术指标序列。" })),
    db: Type.Optional(Type.String({ description: "可选的数据库路径覆盖值。" })),
  },
  { additionalProperties: false },
);

function json(payload: unknown) {
  const summarized = summarizePayload(payload);
  return {
    content: [{ type: "text", text: summarized ?? JSON.stringify(payload, null, 2) }],
    details: payload,
  };
}

function formatNumber(value: unknown, digits = 3): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  return value.toFixed(digits);
}

function formatPct(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  return `${(value * 100).toFixed(2)}%`;
}

export function summarizePayload(payload: unknown): string | undefined {
  if (!payload || typeof payload !== "object") {
    return undefined;
  }
  const record = payload as Record<string, unknown>;
  switch (record.kind) {
    case "etf_search":
      return summarizeEtfSearch(record);
    case "etf_latest_price":
      return summarizeLatestPrice(record);
    case "etf_detail":
      return summarizeEtfDetail(record);
    case "technical_indicators":
      return summarizeTechnicalIndicators(record);
    case "technical_analysis":
      return summarizeTechnicalAnalysis(record);
    default:
      return undefined;
  }
}

function summarizeEtfSearch(record: Record<string, unknown>): string {
  const query = typeof record.query === "string" ? record.query : "";
  const matches = Array.isArray(record.matches) ? record.matches : [];
  const lines = [
    `ETF 检索结果：query=${query}，match_count=${String(record.match_count ?? matches.length)}`,
  ];
  for (const item of matches.slice(0, 10)) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const match = item as Record<string, unknown>;
    lines.push(
      [
        `- symbol=${String(match.symbol ?? "-")}`,
        `name=${String(match.name ?? "-")}`,
        `sector=${String(match.sector_name ?? "-")}`,
        `trade_date=${String(match.latest_trade_date ?? "-")}`,
        `close=${formatNumber(match.latest_close)}`,
      ].join(", "),
    );
  }
  return lines.join("\n");
}

function summarizeLatestPrice(record: Record<string, unknown>): string {
  return [
    "ETF 最新价格：",
    `- symbol=${String(record.symbol ?? "-")}`,
    `- name=${String(record.name ?? "-")}`,
    `- sector=${String(record.sector_name ?? "-")}`,
    `- trade_date=${String(record.trade_date ?? "-")}`,
    `- close=${formatNumber(record.close)}`,
  ].join("\n");
}

function summarizeEtfDetail(record: Record<string, unknown>): string {
  const latestBar =
    record.latest_bar && typeof record.latest_bar === "object"
      ? (record.latest_bar as Record<string, unknown>)
      : undefined;
  const returns =
    record.returns && typeof record.returns === "object"
      ? (record.returns as Record<string, unknown>)
      : undefined;
  const recentBars = Array.isArray(record.recent_bars) ? record.recent_bars : [];
  const latestSignal =
    record.latest_signal && typeof record.latest_signal === "object"
      ? (record.latest_signal as Record<string, unknown>)
      : undefined;
  const technicalAnalysis =
    record.technical_analysis && typeof record.technical_analysis === "object"
      ? (record.technical_analysis as Record<string, unknown>)
      : undefined;

  const lines = [
    "ETF 详情摘要：",
    `- symbol=${String(record.symbol ?? "-")}`,
    `- name=${String(record.name ?? "-")}`,
    `- sector=${String(record.sector_name ?? "-")}`,
  ];
  if (latestBar) {
    lines.push(
      `- latest_bar: trade_date=${String(latestBar.trade_date ?? "-")}, open=${formatNumber(latestBar.open)}, close=${formatNumber(latestBar.close)}, high=${formatNumber(latestBar.high)}, low=${formatNumber(latestBar.low)}, volume=${String(latestBar.volume ?? "-")}`,
    );
  }
  if (returns) {
    const returnParts: string[] = [];
    for (const key of ["1d", "3d", "5d", "20d"]) {
      const value = returns[key];
      if (!value || typeof value !== "object") {
        continue;
      }
      returnParts.push(`${key}=${formatPct((value as Record<string, unknown>).pct_change)}`);
    }
    if (returnParts.length > 0) {
      lines.push(`- returns: ${returnParts.join(", ")}`);
    }
  }
  if (recentBars.length > 0) {
    const compactBars = recentBars
      .slice(-10)
      .map((item) => {
        if (!item || typeof item !== "object") {
          return undefined;
        }
        const bar = item as Record<string, unknown>;
        return `${String(bar.trade_date ?? "-")}:${formatNumber(bar.close)}`;
      })
      .filter(Boolean);
    if (compactBars.length > 0) {
      lines.push(`- recent_closes: ${compactBars.join(", ")}`);
    }
  }
  if (latestSignal) {
    lines.push(
      `- latest_signal: action=${String(latestSignal.action ?? "-")}, trade_date=${String(latestSignal.trade_date ?? "-")}, ma150=${formatNumber(latestSignal.ma150, 4)}`,
    );
  }
  if (technicalAnalysis) {
    const indicators =
      technicalAnalysis.indicators && typeof technicalAnalysis.indicators === "object"
        ? (technicalAnalysis.indicators as Record<string, unknown>)
        : undefined;
    if (indicators) {
      lines.push(
        `- technical: ma_150=${formatNumber(indicators.ma_150, 4)}, macd_hist=${formatNumber(indicators.macd_hist, 4)}, rsi_14=${formatNumber(indicators.rsi_14, 2)}, adx_14=${formatNumber(indicators.adx_14, 2)}`,
      );
    }
  }
  return lines.join("\n");
}

function summarizeTechnicalIndicators(record: Record<string, unknown>): string {
  const indicators =
    record.indicators && typeof record.indicators === "object"
      ? (record.indicators as Record<string, unknown>)
      : undefined;
  return [
    "技术指标摘要：",
    `- symbol=${String(record.symbol ?? "-")}`,
    `- name=${String(record.name ?? "-")}`,
    `- sector=${String(record.sector_name ?? "-")}`,
    `- trade_date=${String(record.trade_date ?? "-")}`,
    `- ma_150=${formatNumber(indicators?.ma_150, 4)}`,
    `- macd_hist=${formatNumber(indicators?.macd_hist, 4)}`,
    `- rsi_14=${formatNumber(indicators?.rsi_14, 2)}`,
    `- adx_14=${formatNumber(indicators?.adx_14, 2)}`,
  ].join("\n");
}

function summarizeTechnicalAnalysis(record: Record<string, unknown>): string {
  const indicators =
    record.indicators && typeof record.indicators === "object"
      ? (record.indicators as Record<string, unknown>)
      : undefined;
  const series = Array.isArray(record.series) ? record.series : [];
  const lines = [
    "技术分析摘要：",
    `- symbol=${String(record.symbol ?? "-")}`,
    `- name=${String(record.name ?? "-")}`,
    `- sector=${String(record.sector_name ?? "-")}`,
    `- trade_date=${String(record.trade_date ?? "-")}`,
    `- ma_150=${formatNumber(indicators?.ma_150, 4)}`,
    `- macd_hist=${formatNumber(indicators?.macd_hist, 4)}`,
    `- rsi_14=${formatNumber(indicators?.rsi_14, 2)}`,
    `- adx_14=${formatNumber(indicators?.adx_14, 2)}`,
  ];
  if (series.length > 0) {
    const compact = series
      .slice(-5)
      .map((item) => {
        if (!item || typeof item !== "object") {
          return undefined;
        }
        const row = item as Record<string, unknown>;
        return `${String(row.trade_date ?? "-")}:ma150=${formatNumber(row.ma_150, 4)}/rsi14=${formatNumber(row.rsi_14, 2)}`;
      })
      .filter(Boolean);
    if (compact.length > 0) {
      lines.push(`- recent_series: ${compact.join(", ")}`);
    }
  }
  return lines.join("\n");
}

function requireString(value: string | undefined, field: string): string {
  const trimmed = value?.trim();
  if (!trimmed) {
    throw new Error(`${field} is required`);
  }
  return trimmed;
}

async function pathExists(targetPath: string): Promise<boolean> {
  try {
    await stat(targetPath);
    return true;
  } catch {
    return false;
  }
}

function resolveTradingPaths(api: OpenClawPluginApi, params: ToolParams) {
  const pluginCfg = (api.pluginConfig ?? {}) as TradingPluginConfig;
  return {
    pythonBin: pluginCfg.pythonBin?.trim() || (process.platform === "win32" ? "python" : "python3"),
    scriptPath: api.resolvePath(
      pluginCfg.scriptPath?.trim() || "../../stock-agent/trading-agent/scripts/stock_agent.py",
    ),
    dbPath: api.resolvePath(
      params.db?.trim() ||
        pluginCfg.dbPath?.trim() ||
        "../../stock-agent/trading-agent/data/industry.db",
    ),
    bundledDbPath: api.resolvePath(
      pluginCfg.bundledDbPath?.trim() || "../../stock-agent/trading-agent/data/industry.db",
    ),
    seedCsvPath: api.resolvePath(
      pluginCfg.seedCsvPath?.trim() ||
        "../../stock-agent/trading-agent/data/industry-etf-candidates.csv",
    ),
  };
}

async function runTradingCommand(params: {
  pythonBin: string;
  scriptPath: string;
  cwd: string;
  args: string[];
}) {
  const { stdout, stderr } = await execFileAsync(
    params.pythonBin,
    [params.scriptPath, ...params.args],
    {
      cwd: params.cwd,
      encoding: "utf8",
      maxBuffer: 10 * 1024 * 1024,
    },
  );
  const text = typeof stdout === "string" ? stdout.trim() : "";
  const stderrText = typeof stderr === "string" ? stderr.trim() : "";
  if (!text) {
    throw new Error(stderrText || "Trading tool returned empty output");
  }
  return JSON.parse(text) as unknown;
}

async function ensureTradingStore(params: {
  pythonBin: string;
  scriptPath: string;
  dbPath: string;
  bundledDbPath: string;
  seedCsvPath: string;
  cwd: string;
}) {
  const dbMissing = !(await pathExists(params.dbPath));
  const bundledExists = await pathExists(params.bundledDbPath);
  if (dbMissing && bundledExists && params.dbPath !== params.bundledDbPath) {
    await mkdir(path.dirname(params.dbPath), { recursive: true });
    await copyFile(params.bundledDbPath, params.dbPath);
  }
  await runTradingCommand({
    pythonBin: params.pythonBin,
    scriptPath: params.scriptPath,
    cwd: params.cwd,
    args: ["bootstrap-db", "--db", params.dbPath, "--csv", params.seedCsvPath],
  });
}

export function buildCommandArgs(params: ToolParams, dbPath: string): string[] {
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
    case "search_etf": {
      const args = ["search-etf", "--db", dbPath, "--query", requireString(params.query, "query")];
      if (typeof params.limit === "number" && Number.isFinite(params.limit)) {
        args.push("--limit", String(Math.trunc(params.limit)));
      }
      return args;
    }
    case "latest_price":
      return ["latest-price", "--db", dbPath, "--symbol", requireString(params.symbol, "symbol")];
    case "etf_detail": {
      const args = [
        "etf-detail",
        "--db",
        dbPath,
        "--symbol",
        requireString(params.symbol, "symbol"),
      ];
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
    case "technical_indicators": {
      const args = [
        "technical-indicators",
        "--db",
        dbPath,
        "--symbol",
        requireString(params.symbol, "symbol"),
      ];
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
    case "technical_analysis": {
      const args = [
        "technical-analysis",
        "--db",
        dbPath,
        "--symbol",
        requireString(params.symbol, "symbol"),
      ];
      if (params.start) {
        args.push("--start", params.start);
      }
      if (params.end) {
        args.push("--end", params.end);
      }
      if (typeof params.recentBars === "number" && Number.isFinite(params.recentBars)) {
        args.push("--recent-bars", String(Math.trunc(params.recentBars)));
      }
      if (params.includeSeries) {
        args.push("--include-series");
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
      "访问 trading-agent 正式运行时，支持日常同步、ETF 搜索、策略日报、涨幅排行、ETF 详情和批量信号查询。",
    parameters: TradingAgentToolSchema,
    async execute(_id: string, rawParams: Record<string, unknown>) {
      const params = rawParams as unknown as ToolParams;
      try {
        const { pythonBin, scriptPath, dbPath, bundledDbPath, seedCsvPath } = resolveTradingPaths(
          api,
          params,
        );
        const commandArgs = buildCommandArgs(params, dbPath);
        const cwd = path.dirname(path.dirname(scriptPath));
        await ensureTradingStore({
          pythonBin,
          scriptPath,
          dbPath,
          bundledDbPath,
          seedCsvPath,
          cwd,
        });
        const parsed = await runTradingCommand({
          pythonBin,
          scriptPath,
          cwd,
          args: commandArgs,
        });
        return json(parsed);
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : `Trading tool execution failed: ${String(error)}`;
        return json({
          kind: "trading_tool_error",
          action: params.action,
          error: message,
        });
      }
    },
  };
}
