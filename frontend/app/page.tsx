/**
 * ResumeMatch main page.
 * Single-page UI for comparing different versions of your resume against a JD.
 */
"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  ResumeUploader,
  ResumeFile,
} from "@/components/resume-match/ResumeUploader";
import { ResultCard } from "@/components/resume-match/ResultCard";
import { analyzeUpload, AnalyzeResponse } from "@/lib/api";

export default function Home() {
  const [jd, setJd] = useState("");
  const [resumes, setResumes] = useState<ResumeFile[]>([]);
  const [results, setResults] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Only files marked as selected go into analysis
  const selectedFiles = resumes.filter((r) => r.selected).map((r) => r.file);

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    setResults(null);

    try {
      const response = await analyzeUpload(selectedFiles, jd);
      setResults(response);
      console.log("Analysis complete:", response);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Analysis failed";
      setError(message);
      console.error("Analysis error:", err);
    } finally {
      setLoading(false);
    }
  };

  const canAnalyze =
    jd.trim().length > 0 && selectedFiles.length > 0 && !loading;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      {/* Header */}
      <header className="border-b bg-white">
        <div className="container mx-auto px-6 py-4 max-w-4xl">
          <h1 className="text-2xl font-bold">ResumeMatch</h1>
          <p className="text-sm text-muted-foreground">
            Find which version of your resume best matches a job description
          </p>
        </div>
      </header>

      {/* Main content */}
      <main className="container mx-auto px-6 py-8 max-w-4xl">
        <div className="space-y-6">
          {/* Resume upload section */}
          <Card>
            <CardHeader>
              <CardTitle>Resume Versions</CardTitle>
            </CardHeader>
            <CardContent>
              <ResumeUploader resumes={resumes} onChange={setResumes} />
            </CardContent>
          </Card>

          {/* JD input section */}
          <Card>
            <CardHeader>
              <CardTitle>Job Description</CardTitle>
            </CardHeader>
            <CardContent>
              <Label htmlFor="jd-input" className="sr-only">
                Job Description
              </Label>
              <Textarea
                id="jd-input"
                placeholder="Paste the job description here..."
                value={jd}
                onChange={(e) => setJd(e.target.value)}
                className="min-h-[200px] resize-none"
              />
              <p className="text-xs text-muted-foreground mt-2">
                {jd.length} characters
              </p>
            </CardContent>
          </Card>

          {/* Analyze button */}
          <div className="flex justify-center">
            <Button
              size="lg"
              onClick={handleAnalyze}
              disabled={!canAnalyze}
              className="min-w-[200px]"
            >
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Analyzing...
                </>
              ) : (
                "Analyze Match"
              )}
            </Button>
          </div>

          {/* Error display */}
          {error && (
            <Card className="border-red-300 bg-red-50">
              <CardContent className="pt-6">
                <p className="text-sm text-red-700">
                  <strong>Error:</strong> {error}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Loading skeleton */}
          {loading && (
            <Card>
              <CardContent className="py-12 text-center">
                <Loader2 className="mx-auto h-8 w-8 animate-spin text-slate-400 mb-3" />
                <p className="text-sm text-muted-foreground">
                  Analyzing {selectedFiles.length} resume version
                  {selectedFiles.length > 1 ? "s" : ""}... (about 15-20s each)
                </p>
              </CardContent>
            </Card>
          )}

          {/* Results */}
          {results && !loading && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold">
                Results
                {results.results.length > 1 &&
                  ` (${results.results.length} versions ranked)`}
              </h2>

              {/* Comparison insight (multi-resume only) */}
              {results.comparison_insight && (
                <Card className="bg-blue-50 border-blue-200">
                  <CardContent className="pt-6">
                    <p className="text-sm text-blue-900">
                      <strong>💡 Recommendation:</strong>{" "}
                      {results.comparison_insight}
                    </p>
                  </CardContent>
                </Card>
              )}

              {/* Result cards */}
              {results.results.map((analysis) => {
                const file = selectedFiles.find(
                  (_, idx) => `resume_${idx + 1}` === analysis.resume_id
                );
                return (
                  <ResultCard
                    key={analysis.resume_id}
                    analysis={analysis}
                    filename={file?.name}
                    isBestMatch={results.best_match_id === analysis.resume_id}
                  />
                );
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}