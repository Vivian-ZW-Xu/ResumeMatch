/**
 * ResumeUploader: vertical list of uploaded resume versions
 * with selection checkboxes for analysis.
 */
"use client";

import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileText, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

export interface ResumeFile {
  file: File;
  selected: boolean;
}

interface ResumeUploaderProps {
  resumes: ResumeFile[];
  onChange: (resumes: ResumeFile[]) => void;
}

export function ResumeUploader({ resumes, onChange }: ResumeUploaderProps) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      // New uploads are selected by default
      const newResumes = acceptedFiles.map((file) => ({
        file,
        selected: true,
      }));
      onChange([...resumes, ...newResumes]);
    },
    [resumes, onChange]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
    },
    multiple: true,
  });

  const toggleSelection = (index: number) => {
    onChange(
      resumes.map((r, i) =>
        i === index ? { ...r, selected: !r.selected } : r
      )
    );
  };

  const removeFile = (index: number) => {
    onChange(resumes.filter((_, i) => i !== index));
  };

  const selectedCount = resumes.filter((r) => r.selected).length;

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`
          border-2 border-dashed rounded-lg p-6 text-center cursor-pointer
          transition-colors
          ${
            isDragActive
              ? "border-blue-500 bg-blue-50"
              : "border-slate-300 hover:border-slate-400 hover:bg-slate-50"
          }
        `}
      >
        <input {...getInputProps()} />
        <Upload className="mx-auto h-8 w-8 text-slate-400 mb-2" />
        {isDragActive ? (
          <p className="text-sm font-medium">Drop the PDF files here...</p>
        ) : (
          <>
            <p className="text-sm font-medium mb-1">
              Drag & drop, or click to browse
            </p>
            <p className="text-xs text-muted-foreground">
              Upload different versions of your resume
            </p>
          </>
        )}
      </div>

      {/* Uploaded files list */}
      {resumes.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-slate-700">
            {selectedCount} of {resumes.length} version
            {resumes.length > 1 ? "s" : ""} selected for analysis
          </p>

          <div className="border rounded-lg divide-y max-h-72 overflow-y-auto">
            {resumes.map((resume, index) => (
              <div
                key={index}
                className={`
                  flex items-center gap-3 px-3 py-2.5
                  ${resume.selected ? "bg-white" : "bg-slate-50 opacity-60"}
                `}
              >
                <Checkbox
                  checked={resume.selected}
                  onCheckedChange={() => toggleSelection(index)}
                  aria-label={`Select ${resume.file.name}`}
                />
                <FileText className="h-4 w-4 text-slate-500 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">
                    {resume.file.name}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {(resume.file.size / 1024).toFixed(1)} KB
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeFile(index)}
                  aria-label="Remove file"
                  className="flex-shrink-0 h-8 w-8 p-0"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}