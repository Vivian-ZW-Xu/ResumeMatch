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
import { JDSummaryCard } from "@/components/resume-match/JDSummaryCard";
import { analyzeUpload, AnalyzeResponse } from "@/lib/api";

// ============================================================
// Sample data for the "Try with sample data" button
// ============================================================

const SAMPLE_FILES = [
  "ZhuweiXu_DataScientist_Resume.pdf",
  "ZhuweiXu_MLE_Resume.pdf",
];
const SAMPLE_JD_PATH = "/samples/tiktok-mle-jd.txt";
const SAMPLE_RESPONSE_PATH = "/samples/sample-response.json";

async function loadSampleFile(filename: string): Promise<File> {
  const response = await fetch(`/samples/${filename}`);
  if (!response.ok) {
    throw new Error(`Failed to load sample file: ${filename}`);
  }
  const blob = await response.blob();
  return new File([blob], filename, { type: "application/pdf" });
}

async function loadSampleJd(): Promise<string> {
  const response = await fetch(SAMPLE_JD_PATH);
  if (!response.ok) {
    throw new Error("Failed to load sample JD");
  }
  return await response.text();
}

// ============================================================
// Main component
// ============================================================

export default function Home() {
  const [jd, setJd] = useState("");
  const [resumes, setResumes] = useState<ResumeFile[]>([]);
  const [results, setResults] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Only files marked as selected go into analysis
  const selectedFiles = resumes.filter((r) => r.selected).map((r) => r.file);

  const handleLoadSample = async () => {
    setError(null);
    try {
      const [files, jdText] = await Promise.all([
        Promise.all(SAMPLE_FILES.map(loadSampleFile)),
        loadSampleJd(),
      ]);

      const sampleResumes: ResumeFile[] = files.map((file) => ({
        file,
        selected: true,
      }));

      setResumes(sampleResumes);
      setJd(jdText);
      setResults(null);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to load sample data";
      setError(message);
    }
  };

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    setResults(null);

    // Detect if we're running with sample data → use cached response
    const isSample =
      selectedFiles.length === SAMPLE_FILES.length &&
      selectedFiles.every((f) => SAMPLE_FILES.includes(f.name));

    try {
      if (isSample) {
        // Brief delay so the loading state is visible
        await new Promise((resolve) => setTimeout(resolve, 1500));

        const response = await fetch(SAMPLE_RESPONSE_PATH);
        if (!response.ok) {
          throw new Error("Failed to load sample response");
        }
        const cached: AnalyzeResponse = await response.json();
        setResults(cached);
        console.log("Sample analysis loaded from cache");
      } else {
        const response = await analyzeUpload(selectedFiles, jd);
        setResults(response);
        console.log("Analysis complete:", response);
      }
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
        <div className="container mx-auto px-6 py-4 max-w-6xl">
          <h1 className="text-2xl font-bold">ResumeMatch</h1>
          <p className="text-sm text-muted-foreground">
            Find which version of your resume best matches a job description
          </p>
        </div>
      </header>

      {/* Main content */}
      <main className="container mx-auto px-6 py-8 max-w-6xl">
        <div className="space-y-6">
          {/* Resume upload + JD input - side by side on desktop, stacked on mobile */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Resume upload (1/3 width on desktop) */}
            <Card className="md:col-span-1 flex flex-col h-[500px]">
              <CardHeader className="flex-shrink-0">
                <CardTitle>Resume Versions</CardTitle>
              </CardHeader>
              <CardContent className="flex-1 min-h-0">
                <ResumeUploader resumes={resumes} onChange={setResumes} />
              </CardContent>
            </Card>

            {/* JD input (2/3 width on desktop) */}
            <Card className="md:col-span-2 flex flex-col h-[500px]">
              <CardHeader className="flex-shrink-0">
                <CardTitle>Job Description</CardTitle>
              </CardHeader>
              <CardContent className="flex-1 min-h-0 flex flex-col">
                <Label htmlFor="jd-input" className="sr-only">
                  Job Description
                </Label>
                <Textarea
                  id="jd-input"
                  placeholder="Paste the job description here..."
                  value={jd}
                  onChange={(e) => setJd(e.target.value)}
                  className="flex-1 resize-none"
                />
                <p className="text-xs text-muted-foreground mt-2 flex-shrink-0">
                  {jd.length} characters
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Analyze + Sample buttons */}
          <div className="flex justify-center gap-3">
            <Button
              variant="outline"
              size="lg"
              onClick={handleLoadSample}
              disabled={loading}
            >
              Try with sample data
            </Button>
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
              {/* JD Summary at top */}
              {results.jd_summary && (
                <JDSummaryCard
                  summary={results.jd_summary}
                  requirements={results.jd_requirements}
                />
              )}
              <h2 className="text-xl font-bold">
                Results
                {results.results.length > 1 &&
                  ` (${results.results.length} versions ranked)`}
              </h2>

              {/* Result cards */}
              {results.results.map((analysis) => {
                const file = selectedFiles.find(
                  (_, idx) => `resume_${idx + 1}` === analysis.resume_id
                );
                const isMultiple = results.results.length > 1;
                const isBest = results.best_match_id === analysis.resume_id;
                return (
                  <ResultCard
                    key={analysis.resume_id}
                    analysis={analysis}
                    jd={jd}
                    filename={file?.name}
                    isBestMatch={isBest}
                    collapsible={isMultiple}
                    defaultExpanded={!isMultiple || isBest}
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