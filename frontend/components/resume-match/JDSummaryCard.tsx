/**
 * JDSummaryCard: displays structured JD information at a glance.
 * Shows company info, location, salary, key skills, etc.
 * Optionally shows hard requirements / nice-to-haves breakdown
 * if jd_requirements is provided.
 */
"use client";

import { useState } from "react";
import {
  Building2,
  MapPin,
  Briefcase,
  Clock,
  DollarSign,
  GraduationCap,
  Wrench,
  Home,
  ChevronDown,
  CheckSquare,
  Star,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { JDSummary, JDRequirements } from "@/lib/api";

interface JDSummaryCardProps {
  summary: JDSummary;
  requirements?: JDRequirements | null;
}

// Truncate threshold for grid items
const TRUNCATE_LENGTH = 60;

function TruncatedValue({ value }: { value: string }) {
  const isLong = value.length > TRUNCATE_LENGTH;
  const displayed = isLong ? value.slice(0, TRUNCATE_LENGTH) + "…" : value;

  return (
    <p
      className="font-medium leading-snug"
      title={isLong ? value : undefined}
    >
      {displayed}
    </p>
  );
}

// ============================================================
// Collapsible requirements section
// ============================================================

interface RequirementsSectionProps {
  requirements: JDRequirements;
}

function RequirementsSection({ requirements }: RequirementsSectionProps) {
  const [open, setOpen] = useState(false);

  const hardCount = requirements.hard_requirements.length;
  const niceCount = requirements.nice_to_haves.length;

  // Don't render if there's nothing to show
  if (hardCount === 0 && niceCount === 0) return null;

  return (
    <div className="pt-2 border-t border-slate-200">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded px-2 -mx-2 transition-colors"
      >
        <span>
          Requirements breakdown ({hardCount} hard
          {niceCount > 0 ? `, ${niceCount} nice-to-have` : ""})
        </span>
        <ChevronDown
          className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="mt-2 space-y-3">
          {hardCount > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-blue-700 mb-1.5">
                <CheckSquare className="h-3 w-3" />
                Hard Requirements
              </div>
              <ul className="space-y-1 pl-1">
                {requirements.hard_requirements.map((req, i) => (
                  <li
                    key={i}
                    className="text-xs text-slate-700 leading-relaxed flex gap-2"
                  >
                    <span className="text-blue-400 flex-shrink-0">•</span>
                    <span>{req}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {niceCount > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-700 mb-1.5">
                <Star className="h-3 w-3" />
                Nice to Have
              </div>
              <ul className="space-y-1 pl-1">
                {requirements.nice_to_haves.map((req, i) => (
                  <li
                    key={i}
                    className="text-xs text-slate-700 leading-relaxed flex gap-2"
                  >
                    <span className="text-amber-400 flex-shrink-0">•</span>
                    <span>{req}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================
// Main component
// ============================================================

export function JDSummaryCard({ summary, requirements }: JDSummaryCardProps) {
  const headerTitle = summary.title || "Job Position";
  const headerSubtitle = summary.company || null;

  // Items to render in the grid (skip if null/empty)
  const items: { icon: React.ReactNode; label: string; value: string }[] = [];

  if (summary.location) {
    items.push({
      icon: <MapPin className="h-4 w-4" />,
      label: "Location",
      value: summary.location,
    });
  }
  if (summary.employment_type) {
    items.push({
      icon: <Briefcase className="h-4 w-4" />,
      label: "Type",
      value: summary.employment_type,
    });
  }
  if (summary.duration) {
    items.push({
      icon: <Clock className="h-4 w-4" />,
      label: "Duration",
      value: summary.duration,
    });
  }
  if (summary.salary) {
    items.push({
      icon: <DollarSign className="h-4 w-4" />,
      label: "Salary",
      value: summary.salary,
    });
  }
  if (summary.education) {
    items.push({
      icon: <GraduationCap className="h-4 w-4" />,
      label: "Education",
      value: summary.education,
    });
  }
  if (summary.work_mode) {
    items.push({
      icon: <Home className="h-4 w-4" />,
      label: "Work mode",
      value: summary.work_mode,
    });
  }

  return (
    <Card className="bg-slate-50 border-slate-200">
      <CardHeader className="pb-3">
        <div className="flex items-start gap-2">
          <Building2 className="h-5 w-5 text-slate-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <CardTitle className="text-base">{headerTitle}</CardTitle>
            {headerSubtitle && (
              <p className="text-sm text-muted-foreground mt-0.5">
                {headerSubtitle}
              </p>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Company brief */}
        {summary.company_brief && (
          <div className="text-sm text-slate-600 italic leading-relaxed border-l-2 border-slate-300 pl-3">
            {summary.company_brief}
          </div>
        )}

        {/* Info grid */}
        {items.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-sm">
            {items.map((item, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-slate-400 flex-shrink-0 mt-0.5">
                  {item.icon}
                </span>
                <div className="min-w-0 flex-1">
                  <span className="text-xs text-muted-foreground">
                    {item.label}
                  </span>
                  <TruncatedValue value={item.value} />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Key skills */}
        {summary.key_skills.length > 0 && (
          <div className="flex items-start gap-2 pt-2 border-t border-slate-200">
            <Wrench className="h-4 w-4 text-slate-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <span className="text-xs text-muted-foreground">Key skills</span>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {summary.key_skills.map((skill, i) => (
                  <Badge
                    key={i}
                    variant="outline"
                    className="bg-white text-xs"
                  >
                    {skill}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* NEW: Requirements breakdown (collapsible) */}
        {requirements && (
          <RequirementsSection requirements={requirements} />
        )}
      </CardContent>
    </Card>
  );
}