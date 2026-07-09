/**
 * VinUni v10 design-system KIT — the Phase-0 composite primitives every partner
 * & university surface consumes. Import from "@/components/kit".
 *
 * Shell (mono): AppShell/Sidebar/Topbar live in @/components/layout.
 * Base (shadcn): button/input/select/… live in @/components/ui.
 * This kit sits on top: cards, KPIs, charts, tables, sheets, panels.
 *
 * See docs/DESIGN.md §1.1.2 (v10) for tokens, type scale, and the data-viz
 * palette. Content is colorful; the shell stays monochrome.
 */

// Containers
export {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardToolbar,
  CardContent,
  CardFooter,
  SectionLabel,
} from "./card";

// Header
export { PageHeader } from "@/components/layout/page-header";

// KPIs / stats
export { KpiTile, KpiRow, StatCard } from "./kpi";
export type { KpiTileProps, KpiDelta } from "./kpi";

// Hero
export { GradientHeroCard } from "./hero-card";

// Status / chips
export { StatusChip, ToneDot } from "./status-chip";
export type { ChipTone, StatusChipProps } from "./status-chip";

// Queues / activity
export { AttentionPanel } from "./attention-panel";
export type { AttentionItem } from "./attention-panel";
export { ActivityFeed, Timeline } from "./activity-feed";
export type { ActivityEntry } from "./activity-feed";

// Toolbar
export { FilterBar } from "./filter-bar";

// Right-edge detail drawer
export { DetailSheet, DetailSheetSection, DetailRow } from "./detail-sheet";

// Data table (TanStack)
export { DataTable } from "./data-table";
export type { DataTableProps, ColumnDef } from "./data-table";

// Command palette (⌘K)
export { CommandPalette } from "./command-palette";
export type { CommandAction } from "./command-palette";

// Charts (content data-viz)
export {
  AreaChart,
  LineChart,
  MultiLineChart,
  BarChart,
  StackedBar,
  HorizontalBars,
  FunnelChart,
  DonutChart,
  RadialChart,
  Sparkline,
  CalendarHeatmap,
  VIZ,
  VIZ_SERIES,
  VIZ_SEMANTIC,
  seriesColor,
} from "./charts";
export type {
  SeriesDef,
  ChartDatum,
  HorizontalBarDatum,
  FunnelStage,
  DonutSlice,
  HeatmapDatum,
  VizHue,
} from "./charts";

// Honest state primitive (re-export from the shared ui set).
export { EmptyState } from "@/components/ui";
export type { EmptyStateProps, StateKind } from "@/components/ui";
