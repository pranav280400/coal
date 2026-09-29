import {
  Bell,
  ChartColumn,
  CircleHelp,
  ClipboardCheck,
  ClipboardList,
  Factory,
  FileCheck2,
  FileText,
  HardHat,
  LayoutGrid,
  Leaf,
  MapPin,
  MessageSquareWarning,
  ScrollText,
  Settings,
  Sparkle,
  TriangleAlert,
  UserCheck,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";

export interface NavChild {
  href: string;
  label: string;
  perm?: string;
}

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  perm?: string;
  badge?: "notifications";
  children?: NavChild[];
}

/** Everyday work, in the order people use it. */
export const NAV_MAIN: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutGrid },
  { href: "/compliance", label: "Compliance", icon: FileCheck2 },
  {
    href: "/inspections",
    label: "Inspections",
    icon: ClipboardCheck,
    children: [
      { href: "/inspections", label: "All inspections" },
      { href: "/inspections/new", label: "New inspection", perm: "inspection:write" },
    ],
  },
  { href: "/violations", label: "Violations", icon: TriangleAlert },
  { href: "/corrective-actions", label: "Corrective Actions", icon: Wrench },
  { href: "/contractors", label: "Contractors", icon: HardHat },
  { href: "/attendance", label: "Attendance", icon: UserCheck },
  { href: "/grievances", label: "Grievances", icon: MessageSquareWarning },
  { href: "/production", label: "Production", icon: Factory },
  { href: "/environment", label: "Environment", icon: Leaf },
  { href: "/reports", label: "Reports & Analytics", icon: ChartColumn },
  { href: "/assistant", label: "AI Assistant", icon: Sparkle, perm: "ai:use" },
  { href: "/map", label: "Maps & Locations", icon: MapPin },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/notifications", label: "Notifications", icon: Bell, badge: "notifications" },
];

/** Administration and help — out of the way of daily work. */
export const NAV_OTHER: NavItem[] = [
  { href: "/users", label: "Users & Access", icon: Users, perm: "user:admin" },
  { href: "/audit", label: "Audit Logs", icon: ScrollText, perm: "audit:read" },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/help", label: "Help", icon: CircleHelp },
];

export const NAV: NavItem[] = [...NAV_MAIN, ...NAV_OTHER];

/** Things people create from anywhere (mobile "+" button, empty states). */
export const QUICK_ACTIONS: { href: string; label: string; hint: string; icon: LucideIcon; perm: string }[] = [
  { href: "/inspections/new", label: "New inspection", hint: "Record a site inspection with photos", icon: ClipboardList, perm: "inspection:write" },
  { href: "/violations/new", label: "Report a violation", hint: "Log a problem found at the mine", icon: TriangleAlert, perm: "violation:write" },
  { href: "/grievances?new=1", label: "Raise a grievance", hint: "Complaint about wages, safety or welfare", icon: MessageSquareWarning, perm: "grievance:raise" },
  { href: "/environment?new=1", label: "Record reading", hint: "Air, noise or water measurement", icon: Leaf, perm: "operations:write" },
  { href: "/attendance", label: "Record check-in", hint: "Mark a worker present for the shift", icon: UserCheck, perm: "attendance:write" },
];

export function isActive(pathname: string, href: string): boolean {
  return href === "/dashboard" ? pathname === "/dashboard" : pathname === href || pathname.startsWith(`${href}/`);
}

/** Sidebar sections: NAV_MAIN split by the kind of work, in reading order. */
export const NAV_GROUPS: { label: string; hrefs: string[] }[] = [
  { label: "Overview", hrefs: ["/dashboard", "/reports", "/assistant", "/map"] },
  { label: "Operations", hrefs: ["/compliance", "/inspections", "/violations", "/corrective-actions", "/production", "/environment"] },
  { label: "People", hrefs: ["/contractors", "/attendance", "/grievances"] },
  { label: "Records", hrefs: ["/documents", "/notifications"] },
];
