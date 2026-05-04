/**
 * ResultCard: displays the full analysis result for a single resume.
 * Includes radar chart, dimension breakdown, strengths, and gaps.
 * Supports collapsible mode for multi-resume comparison.
 * Strengths and Gaps sections are also independently collapsible.
 */
"use client";

import { useState } from "react";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
} from "recharts";
import { CheckCircle2, AlertCircle, Trophy, ChevronDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { ResumeAnalysis } from "@/lib/api";

// ============================================================
// Helper component: collapsible section (for Strengths/Gaps)
// ============================================================

interface CollapsibleSectionProps {
  title: string;
  icon: React.ReactNode;
  colorClass: string;
  children: React.ReactNode;
}

function CollapsibleSection({
  title,
  icon,
  colorClass,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`w-full flex items-center justify-between gap-2 py-2 text-sm font-semibold ${colorClass} hover:bg-slate-50 rounded px-2 -mx-2 transition-colors`}
      >
        <span className="flex items-center gap-2">
          {icon}
          {title}
        </span>
        <ChevronDown
          className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && <div className="mt-3">{children}</div>}
    </div>
  );
}

// ============================================================
// Main component: ResultCard
// ============================================================

interface ResultCardProps {
  analysis: ResumeAnalysis;
  filename?: string;
  isBestMatch?: boolean;
  collapsible?: boolean;
  defaultExpanded?: boolean;
}

export function ResultCard({
  analysis,
  filename,
  isBestMatch,
  collapsible = false,
  defaultExpanded = true,
}: ResultCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  // Format data for radar chart
  const radarData = [
    { dimension: "Skills", value: analysis.dimension_scores.skills },
    { dimension: "Experience", value: analysis.dimension_scores.experience },
    { dimension: "Education", value: analysis.dimension_scores.education },
    { dimension: "Industry", value: analysis.dimension_scores.industry },
  ];

  // Score color based on value
  const scoreColor = (score: number) => {
    if (score >= 80) return "text-green-600";
    if (score >= 60) return "text-yellow-600";
    return "text-red-600";
  };

  const handleHeaderClick = () => {
    if (collapsible) {
      setExpanded((prev) => !prev);
    }
  };

  return (
    <Card className={isBestMatch ? "border-blue-500 border-2" : ""}>
      <CardHeader
        className={collapsible ? "cursor-pointer hover:bg-slate-50" : ""}
        onClick={handleHeaderClick}
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <CardTitle className="text-base truncate">
                {filename || analysis.resume_id}
              </CardTitle>
              {isBestMatch && (
                <Badge className="bg-blue-500 text-white hover:bg-blue-600 flex-shrink-0">
                  <Trophy className="h-3 w-3 mr-1" />
                  Best Version
                </Badge>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            <div className="text-right">
              <div
                className={`text-3xl font-bold leading-none ${scoreColor(
                  analysis.overall_score
                )}`}
              >
                {analysis.overall_score}
              </div>
              <div className="text-xs text-muted-foreground">/ 100</div>
            </div>
            {collapsible && (
              <ChevronDown
                className={`h-5 w-5 text-slate-400 transition-transform ${
                  expanded ? "rotate-180" : ""
                }`}
              />
            )}
          </div>
        </div>
      </CardHeader>

      {expanded && (
        <CardContent className="space-y-6">
          {/* Summary */}
          <p className="text-sm leading-relaxed text-slate-700">
            {analysis.summary}
          </p>

          {/* Radar chart + dimension scores */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarData}>
                  <PolarGrid />
                  <PolarAngleAxis
                    dataKey="dimension"
                    tick={{ fontSize: 12 }}
                  />
                  <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} />
                  <Radar
                    name="Score"
                    dataKey="value"
                    stroke="#3b82f6"
                    fill="#3b82f6"
                    fillOpacity={0.4}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            <div className="space-y-3">
              {radarData.map((d) => (
                <div key={d.dimension}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="font-medium">{d.dimension}</span>
                    <span className={scoreColor(d.value)}>{d.value}/100</span>
                  </div>
                  <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 transition-all"
                      style={{ width: `${d.value}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Strengths (collapsible) */}
          {analysis.strengths.length > 0 && (
            <CollapsibleSection
              title={`Strengths (${analysis.strengths.length})`}
              icon={<CheckCircle2 className="h-4 w-4" />}
              colorClass="text-green-700"
            >
              <div className="space-y-3">
                {analysis.strengths.map((s, i) => (
                  <div
                    key={i}
                    className="border-l-2 border-green-300 pl-4 space-y-1"
                  >
                    <p className="text-sm font-medium">{s.point}</p>
                    {s.resume_excerpt && (
                      <p className="text-xs text-muted-foreground italic">
                        📄 &quot;{s.resume_excerpt}&quot;
                      </p>
                    )}
                    {s.jd_excerpt && (
                      <p className="text-xs text-muted-foreground italic">
                        📋 JD: &quot;{s.jd_excerpt}&quot;
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </CollapsibleSection>
          )}

          {/* Gaps (collapsible) */}
          {analysis.gaps.length > 0 && (
            <CollapsibleSection
              title={`Gaps (${analysis.gaps.length})`}
              icon={<AlertCircle className="h-4 w-4" />}
              colorClass="text-amber-700"
            >
              <div className="space-y-3">
                {analysis.gaps.map((g, i) => (
                  <div
                    key={i}
                    className="border-l-2 border-amber-300 pl-4 space-y-1"
                  >
                    <p className="text-sm font-medium">{g.point}</p>
                    {g.jd_excerpt && (
                      <p className="text-xs text-muted-foreground italic">
                        📋 JD requires: &quot;{g.jd_excerpt}&quot;
                      </p>
                    )}
                    {g.resume_excerpt && (
                      <p className="text-xs text-muted-foreground italic">
                        📄 Resume says: &quot;{g.resume_excerpt}&quot;
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </CollapsibleSection>
          )}
        </CardContent>
      )}
    </Card>
  );
}