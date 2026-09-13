import {
  Activity,
  Crosshair,
  Database,
  FlaskConical,
  GitBranch,
  LayoutDashboard,
  ListTree,
  Scale,
  Settings,
  ShieldAlert,
  Tags,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** SPEC.md §10 phase in which the backend for this page lands. */
  phase: number;
  group: "observe" | "evaluate" | "secure" | "manage";
  shortcut?: string;
}

export const NAV: NavItem[] = [
  {
    href: "/",
    label: "Overview",
    icon: LayoutDashboard,
    phase: 2,
    group: "observe",
    shortcut: "g o",
  },
  { href: "/traces", label: "Traces", icon: ListTree, phase: 2, group: "observe", shortcut: "g t" },
  {
    href: "/trajectories",
    label: "Trajectories",
    icon: GitBranch,
    phase: 2,
    group: "observe",
    shortcut: "g j",
  },
  {
    href: "/live",
    label: "Live feed",
    icon: Activity,
    phase: 2,
    group: "observe",
    shortcut: "g l",
  },
  { href: "/evaluations", label: "Evaluations", icon: FlaskConical, phase: 3, group: "evaluate" },
  { href: "/judges", label: "Judge quality", icon: Scale, phase: 4, group: "evaluate" },
  { href: "/labelling", label: "Labelling", icon: Tags, phase: 4, group: "evaluate" },
  { href: "/datasets", label: "Datasets", icon: Database, phase: 4, group: "evaluate" },
  { href: "/redteam", label: "Red team", icon: Crosshair, phase: 5, group: "secure" },
  { href: "/security", label: "Security", icon: ShieldAlert, phase: 6, group: "secure" },
  { href: "/settings", label: "Settings", icon: Settings, phase: 2, group: "manage" },
];

/** Phases whose backend exists in this build. Pages for later phases render honest empty states. */
export const IMPLEMENTED_PHASE = 6;

export const GROUP_LABEL: Record<NavItem["group"], string> = {
  observe: "Observe",
  evaluate: "Evaluate",
  secure: "Secure",
  manage: "Manage",
};
