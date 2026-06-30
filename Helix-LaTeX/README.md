# Helix — Specialization Project Report (LaTeX)

Overleaf-ready LaTeX source matching the MCA Specialization Project guideline format
(Times New Roman, A4, 1″ margins, 1.15 line spacing, 16 pt centered chapter
headings, 12 pt bold section headings, chapter-relative Table 2.1 / Figure 3.1
numbering, auto Table of Contents / List of Figures / List of Tables).

## Open on Overleaf
1. Overleaf → **New Project → Upload Project** → select `Helix-LaTeX.zip`
   (or upload this whole folder).
2. Set the compiler to **pdfLaTeX** (Menu → Compiler). 
3. Click **Recompile**. The TOC / LoF / LoT fill automatically (Overleaf runs the
   needed passes).

## Files
- `main.tex` — the full report (Chapters 1–3: Introduction, System Analysis &
  Requirements, System Design).
- `media/image1.png` — title-page logo (from the original template; replace with
  the CHRIST logo if needed).

## Diagrams
All seven design diagrams are drawn natively in **TikZ** (vector, no image files):
block/context, three-tier architecture, module dependency graph, DFD levels 0/1/2,
and the ER diagram. They scale to any zoom and are editable in `main.tex`.

## To fill in
- `<Guide Name>` on the title and certificate pages.
- Two **report-screen** placeholders remain as bordered boxes (Conversation/Run
  export, Deep Reasoning run summary) — drop screenshots in by replacing each
  `\fbox{...}` with `\includegraphics{...}`.
