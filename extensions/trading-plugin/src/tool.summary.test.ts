import { describe, expect, it } from "vitest";
import { summarizePayload } from "./tool.js";

describe("trading_agent payload summaries", () => {
  it("summarizes latest_price payload", () => {
    const text = summarizePayload({
      kind: "etf_latest_price",
      symbol: "159611",
      name: "电力ETF",
      sector_name: "电力",
      trade_date: "2026-03-12",
      close: 1.205,
    });

    expect(text).toContain("ETF 最新价格");
    expect(text).toContain("symbol=159611");
    expect(text).toContain("trade_date=2026-03-12");
  });

  it("summarizes etf_detail payload", () => {
    const text = summarizePayload({
      kind: "etf_detail",
      symbol: "159611",
      name: "电力ETF",
      sector_name: "电力",
      latest_bar: {
        trade_date: "2026-03-12",
        open: 1.178,
        close: 1.205,
        high: 1.21,
        low: 1.172,
        volume: 6412053,
      },
      returns: {
        "1d": { pct_change: 0.0229 },
        "3d": { pct_change: 0.0478 },
        "5d": { pct_change: 0.073 },
      },
      recent_bars: [
        { trade_date: "2026-03-10", close: 1.149 },
        { trade_date: "2026-03-11", close: 1.178 },
        { trade_date: "2026-03-12", close: 1.205 },
      ],
      latest_signal: {
        action: "hold",
        trade_date: "2026-03-12",
        ma150: 1.0358,
      },
      technical_analysis: {
        indicators: {
          ma_150: 1.0358,
          macd_hist: 0.0123,
          rsi_14: 61.5,
          adx_14: 28.6,
        },
      },
    });

    expect(text).toContain("ETF 详情摘要");
    expect(text).toContain("recent_closes");
    expect(text).toContain("latest_signal");
    expect(text).toContain("technical:");
  });

  it("summarizes technical_indicators payload", () => {
    const text = summarizePayload({
      kind: "technical_indicators",
      symbol: "159611",
      name: "电力ETF",
      sector_name: "电力",
      trade_date: "2026-03-12",
      indicators: {
        ma_150: 1.0358,
        macd_hist: 0.0123,
        rsi_14: 61.5,
        adx_14: 28.6,
      },
    });

    expect(text).toContain("技术指标摘要");
    expect(text).toContain("ma_150=1.0358");
  });

  it("summarizes technical_analysis payload", () => {
    const text = summarizePayload({
      kind: "technical_analysis",
      symbol: "159611",
      name: "电力ETF",
      sector_name: "电力",
      trade_date: "2026-03-12",
      indicators: {
        ma_150: 1.0358,
        macd_hist: 0.0123,
        rsi_14: 61.5,
        adx_14: 28.6,
      },
      series: [
        { trade_date: "2026-03-11", ma_150: 1.029, rsi_14: 59.8 },
        { trade_date: "2026-03-12", ma_150: 1.0358, rsi_14: 61.5 },
      ],
    });

    expect(text).toContain("技术分析摘要");
    expect(text).toContain("recent_series");
  });
});
