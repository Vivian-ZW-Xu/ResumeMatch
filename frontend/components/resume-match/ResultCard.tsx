/**
 * ResultCard: displays the full analysis result for a single resume.
 * Includes radar chart, dimension breakdown, strengths, and gaps.
 */
"use client";

import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
} from "recharts";
import { CheckCircle2, AlertCircle, Trophy } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { ResumeAnalysis } from "@/lib/api";

interface ResultCardProps {
  analysis: ResumeAnalysis;
  filename?: string;
  isBestMatch?: boolean;
}

export function ResultCard({
  analysis,
  filename,
  isBestMatch,
}: ResultCardProps) {
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

  return (
    <Card className={isBestMatch ? "border-blue-500 border-2" : ""}>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <CardTitle className="text-base">
                {filename || analysis.resume_id}
              </CardTitle>
              {isBestMatch && (
                <Badge className="bg-blue-500 text-white hover:bg-blue-600">
                    <Trophy className="h-3 w-3 mr-1" />
                    Best Version
                </Badge>
              )}
            </div>
          </div>
          <div className="text-right">
            <div className={`text-3xl font-bold ${scoreColor(analysis.overall_score)}`}>
              {analysis.overall_score}
            </div>
            <div className="text-xs text-muted-foreground">/ 100</div>
          </div>
        </div>
      </CardHeader>

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

        {/* Strengths */}
        {analysis.strengths.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2 text-green-700">
              <CheckCircle2 className="h-4 w-4" />
              Strengths ({analysis.strengths.length})
            </h3>
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
          </div>
        )}

        {/* Gaps */}
        {analysis.gaps.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2 text-amber-700">
              <AlertCircle className="h-4 w-4" />
              Gaps ({analysis.gaps.length})
            </h3>
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
          </div>
        )}
      </CardContent>
    </Card>
  );
}