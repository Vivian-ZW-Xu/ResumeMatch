/**
 * ResumeUploader: vertical list of uploaded resume versions
 * with selection checkboxes for analysis.
 * Uses fixed-height layout: small dropzone + scrollable file list.
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
    <div className="flex flex-col h-full gap-3">
      {/* Compact drop zone */}
      <div
        {...getRootProps()}
        className={`
          border-2 border-dashed rounded-lg p-4 text-center cursor-pointer
          transition-colors flex-shrink-0
          ${
            isDragActive
              ? "border-blue-500 bg-blue-50"
              : "border-slate-300 hover:border-slate-400 hover:bg-slate-50"
          }
        `}
      >
        <input {...getInputProps()} />
        <Upload className="mx-auto h-6 w-6 text-slate-400 mb-1" />
        {isDragActive ? (
          <p className="text-xs font-medium">Drop here...</p>
        ) : (
          <>
            <p className="text-xs font-medium">Drag & drop, or click</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Upload resume versions
            </p>
          </>
        )}
      </div>

      {/* File count */}
      {resumes.length > 0 && (
        <p className="text-xs font-medium text-slate-700 flex-shrink-0">
          {selectedCount} of {resumes.length} selected
        </p>
      )}

      {/* Scrollable file list - takes remaining space */}
      {resumes.length > 0 && (
        <div className="border rounded-lg divide-y flex-1 overflow-y-auto min-h-0">
          {resumes.map((resume, index) => (
            <div
              key={index}
              className={`
                flex items-center gap-2 px-3 py-2.5
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
                className="flex-shrink-0 h-7 w-7 p-0"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Empty state when no files */}
      {resumes.length === 0 && (
        <div className="flex-1 flex items-center justify-center text-center text-xs text-muted-foreground">
          No resume versions uploaded yet
        </div>
      )}
    </div>
  );
}