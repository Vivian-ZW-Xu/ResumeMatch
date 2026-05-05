/**
 * ResultCard: displays the full analysis result for a single resume.
 * Includes radar chart, dimension breakdown, strengths, gaps,
 * and rubric evaluation transparency.
 * Each gap has a "Get suggestion" button to fetch improvement advice.
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
import {
  CheckCircle2,
  AlertCircle,
  Trophy,
  ChevronDown,
  Lightbulb,
  Loader2,
  ListChecks,
  Check,
  CircleDashed,
  X,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  suggestImprovement,
  type ResumeAnalysis,
  type MatchEvidence,
  type RubricResult,
} from "@/lib/api";

// ============================================================
// Helper: collapsible section
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
// Helper: gap item with "Get suggestion" button
// ============================================================

interface GapItemProps {
  gap: MatchEvidence;
  resumeContent: string;
  jd: string;
}

function GapItem({ gap, resumeContent, jd }: GapItemProps) {
  const [suggestion, setSuggestion] = useState<{
    suggestion: string;
    rewritten_bullet?: string | null;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSuggestion = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await suggestImprovement({
        resume_content: resumeContent,
        jd,
        gap_point: gap.point,
        gap_jd_excerpt: gap.jd_excerpt,
        gap_resume_excerpt: gap.resume_excerpt,
      });
      setSuggestion(result);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to get suggestion";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="border-l-2 border-amber-300 pl-4 space-y-1">
      <p className="text-sm font-medium">{gap.point}</p>
      {gap.jd_excerpt && (
        <p className="text-xs text-muted-foreground italic">
          📋 JD requires: &quot;{gap.jd_excerpt}&quot;
        </p>
      )}
      {gap.resume_excerpt && (
        <p className="text-xs text-muted-foreground italic">
          📄 Resume says: &quot;{gap.resume_excerpt}&quot;
        </p>
      )}

      {!suggestion && !loading && (
        <Button
          variant="outline"
          size="sm"
          onClick={fetchSuggestion}
          className="mt-2 h-7 text-xs"
        >
          <Lightbulb className="h-3 w-3 mr-1" />
          Get suggestion
        </Button>
      )}

      {loading && (
        <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          Generating suggestion...
        </div>
      )}

      {error && (
        <div className="mt-2 text-xs text-red-600">
          Error: {error}
        </div>
      )}

      {suggestion && (
        <div className="mt-3 bg-amber-50 border border-amber-200 rounded p-3 space-y-2">
          <p className="text-xs font-semibold text-amber-900 flex items-center gap-1">
            <Lightbulb className="h-3 w-3" />
            Suggestion
          </p>
          <p className="text-sm text-slate-700 leading-relaxed">
            {suggestion.suggestion}
          </p>
          {suggestion.rewritten_bullet && (
            <div className="mt-2 pt-2 border-t border-amber-200">
              <p className="text-xs font-semibold text-amber-900 mb-1">
                Suggested rewrite:
              </p>
              <p className="text-sm text-slate-800 italic bg-white px-3 py-2 rounded border border-amber-200">
                {suggestion.rewritten_bullet}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================
// Helper: rubric result item (yes/partial/no badge)
// ============================================================

function RubricItem({ result }: { result: RubricResult }) {
  // verdict → icon, color, label
  const verdictMeta = {
    yes: {
      icon: <Check className="h-3.5 w-3.5" />,
      bg: "bg-green-100 text-green-700 border-green-300",
      label: "Yes",
    },
    partial: {
      icon: <CircleDashed className="h-3.5 w-3.5" />,
      bg: "bg-amber-100 text-amber-700 border-amber-300",
      label: "Partial",
    },
    no: {
      icon: <X className="h-3.5 w-3.5" />,
      bg: "bg-red-100 text-red-700 border-red-300",
      label: "No",
    },
  }[result.verdict];

  return (
    <div className="flex items-start gap-2 py-1.5">
      <span
        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-xs font-medium flex-shrink-0 ${verdictMeta.bg}`}
      >
        {verdictMeta.icon}
        {verdictMeta.label}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-slate-700">{result.criterion}</p>
        {result.evidence && (
          <p className="text-xs text-muted-foreground italic mt-0.5">
            📄 &quot;{result.evidence}&quot;
          </p>
        )}
        {result.reasoning && result.verdict !== "yes" && (
          <p className="text-xs text-slate-500 mt-0.5">
            {result.reasoning}
          </p>
        )}
      </div>
    </div>
  );
}

// ============================================================
// Main component
// ============================================================

interface ResultCardProps {
  analysis: ResumeAnalysis;
  jd: string;
  filename?: string;
  isBestMatch?: boolean;
  collapsible?: boolean;
  defaultExpanded?: boolean;
}

export function ResultCard({
  analysis,
  jd,
  filename,
  isBestMatch,
  collapsible = false,
  defaultExpanded = true,
}: ResultCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const radarData = [
    { dimension: "Skills", value: analysis.dimension_scores.skills },
    { dimension: "Experience", value: analysis.dimension_scores.experience },
    { dimension: "Education", value: analysis.dimension_scores.education },
    { dimension: "Industry", value: analysis.dimension_scores.industry },
  ];

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

  // Rubric summary (e.g. "5 / 7 met")
  const rubricSummary = (() => {
    const total = analysis.rubric_results.length;
    if (total === 0) return null;
    const yesCount = analysis.rubric_results.filter(
      (r) => r.verdict === "yes"
    ).length;
    const partialCount = analysis.rubric_results.filter(
      (r) => r.verdict === "partial"
    ).length;
    return { total, yesCount, partialCount };
  })();

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
                  <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 12 }} />
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

          {/* Rubric breakdown (collapsible) — NEW */}
          {rubricSummary && (
            <CollapsibleSection
              title={`Rubric Evaluation (${rubricSummary.yesCount} of ${rubricSummary.total} met${
                rubricSummary.partialCount > 0
                  ? `, ${rubricSummary.partialCount} partial`
                  : ""
              })`}
              icon={<ListChecks className="h-4 w-4" />}
              colorClass="text-blue-700"
            >
              <div className="space-y-1 divide-y divide-slate-100">
                {analysis.rubric_results.map((rr) => (
                  <RubricItem key={rr.id} result={rr} />
                ))}
              </div>
            </CollapsibleSection>
          )}

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

          {/* Gaps (collapsible, with suggestion buttons) */}
          {analysis.gaps.length > 0 && (
            <CollapsibleSection
              title={`Gaps (${analysis.gaps.length})`}
              icon={<AlertCircle className="h-4 w-4" />}
              colorClass="text-amber-700"
            >
              <div className="space-y-4">
                {analysis.gaps.map((g, i) => (
                  <GapItem
                    key={i}
                    gap={g}
                    resumeContent={analysis.resume_content}
                    jd={jd}
                  />
                ))}
              </div>
            </CollapsibleSection>
          )}
        </CardContent>
      )}
    </Card>
  );
}