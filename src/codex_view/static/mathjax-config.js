window.MathJax = {
  loader: { load: ["ui/safe"] },
  tex: { inlineMath: [["\\(", "\\)"]], displayMath: [["\\[", "\\]"]], processEscapes: true },
  svg: { fontCache: "local" },
  options: { safeOptions: { allow: { URLs: "none", classes: "none", cssIDs: "none", styles: "none" } } },
  startup: { typeset: false }
};
