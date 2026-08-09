// Copies pinned npm package dist files into static/vendor/ so templates can
// load them locally instead of from a CDN. Every version lives in package.json
// (devDependencies) — this script never chooses a version itself.
//
// Run via `npm run vendor` (after `npm install`).

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const NODE_MODULES = path.join(ROOT, "node_modules");
const VENDOR_DIR = path.join(ROOT, "static", "vendor");

function copyFile(src, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
}

function copyDir(src, dest) {
  fs.cpSync(src, dest, { recursive: true });
}

function nm(...parts) {
  return path.join(NODE_MODULES, ...parts);
}

function vendor(...parts) {
  return path.join(VENDOR_DIR, ...parts);
}

// ---- 1. Reset static/vendor/ ----------------------------------------------
fs.rmSync(VENDOR_DIR, { recursive: true, force: true });
fs.mkdirSync(VENDOR_DIR, { recursive: true });

// ---- 2. Plain JS/CSS library files -----------------------------------------
const FILE_COPIES = [
  // jQuery
  [nm("jquery", "dist", "jquery.min.js"), vendor("jquery", "jquery.min.js")],

  // SweetAlert2
  [nm("sweetalert2", "dist", "sweetalert2.all.min.js"), vendor("sweetalert2", "sweetalert2.all.min.js")],
  [nm("sweetalert2", "dist", "sweetalert2.min.css"), vendor("sweetalert2", "sweetalert2.min.css")],

  // Select2
  [nm("select2", "dist", "js", "select2.min.js"), vendor("select2", "select2.min.js")],
  [nm("select2", "dist", "css", "select2.min.css"), vendor("select2", "select2.min.css")],

  // Chart.js
  [nm("chart.js", "dist", "chart.umd.min.js"), vendor("chartjs", "chart.umd.min.js")],

  // Lucide icons
  [nm("lucide", "dist", "umd", "lucide.min.js"), vendor("lucide", "lucide.min.js")],

  // Font Awesome 6 (free)
  [nm("@fortawesome", "fontawesome-free", "css", "all.min.css"), vendor("fontawesome", "css", "all.min.css")],

  // Alpine.js
  [nm("alpinejs", "dist", "cdn.min.js"), vendor("alpinejs", "cdn.min.js")],

  // DataTables core
  [nm("datatables.net", "js", "jquery.dataTables.min.js"), vendor("datatables", "jquery.dataTables.min.js")],
  [nm("datatables.net-dt", "css", "jquery.dataTables.min.css"), vendor("datatables", "jquery.dataTables.min.css")],

  // DataTables Buttons extension
  [nm("datatables.net-buttons", "js", "dataTables.buttons.min.js"), vendor("datatables", "buttons", "dataTables.buttons.min.js")],
  [nm("datatables.net-buttons", "js", "buttons.html5.min.js"), vendor("datatables", "buttons", "buttons.html5.min.js")],
  [nm("datatables.net-buttons", "js", "buttons.print.min.js"), vendor("datatables", "buttons", "buttons.print.min.js")],
  [nm("datatables.net-buttons-dt", "css", "buttons.dataTables.min.css"), vendor("datatables", "buttons", "buttons.dataTables.min.css")],

  // DataTables Responsive extension
  [nm("datatables.net-responsive", "js", "dataTables.responsive.min.js"), vendor("datatables", "responsive", "dataTables.responsive.min.js")],
  [nm("datatables.net-responsive-dt", "css", "responsive.dataTables.min.css"), vendor("datatables", "responsive", "responsive.dataTables.min.css")],

  // JSZip / pdfmake / jsPDF / html2canvas (DataTables export buttons + PDF generation)
  [nm("jszip", "dist", "jszip.min.js"), vendor("jszip", "jszip.min.js")],
  [nm("pdfmake", "build", "pdfmake.min.js"), vendor("pdfmake", "pdfmake.min.js")],
  [nm("pdfmake", "build", "vfs_fonts.js"), vendor("pdfmake", "vfs_fonts.js")],
  [nm("jspdf", "dist", "jspdf.umd.min.js"), vendor("jspdf", "jspdf.umd.min.js")],
  [nm("html2canvas", "dist", "html2canvas.min.js"), vendor("html2canvas", "html2canvas.min.js")],

  // pdf.js
  [nm("pdfjs-dist", "build", "pdf.min.js"), vendor("pdfjs", "pdf.min.js")],
  [nm("pdfjs-dist", "build", "pdf.worker.min.js"), vendor("pdfjs", "pdf.worker.min.js")],
];

for (const [src, dest] of FILE_COPIES) {
  copyFile(src, dest);
}

// ---- 3. Directory copies (webfonts / flag SVGs / sort icons) --------------
copyDir(nm("@fortawesome", "fontawesome-free", "webfonts"), vendor("fontawesome", "webfonts"));
copyFile(nm("flag-icons", "css", "flag-icons.min.css"), vendor("flag-icons", "css", "flag-icons.min.css"));
copyDir(nm("flag-icons", "flags"), vendor("flag-icons", "flags"));
copyDir(nm("datatables.net-dt", "images"), vendor("datatables", "images"));

// ---- 4. Fonts ---------------------------------------------------------------
// Each fontsource package declares font-family as "<Name> Variable" (variable
// packages) — the project's templates/CSS reference the plain Google Fonts
// name (e.g. "Inter"), so we strip the " Variable" suffix when copying.
//
// The Tailwind CLI (Lightning CSS) inlines local `@import`s verbatim without
// rebasing relative url()s to the output file's location, so a font CSS's
// `url(./files/x.woff2)` would resolve against static/css/ (wrong) once
// bundled into a compiled stylesheet there. Every compiled entry point lands
// in static/css/, and every vendored font lives in static/vendor/fonts/<dir>/,
// so we rewrite the url()s ourselves to the one relative path that's correct
// from any of them: ../vendor/fonts/<dir>/files/...
function buildFontCss(sourceCssFiles, destCssPath, destFilesDir, familyDir, dirName) {
  let combined = "";
  for (const cssPath of sourceCssFiles) {
    combined += fs.readFileSync(cssPath, "utf8") + "\n";
  }
  combined = combined.replace(/font-family: '([^']+) Variable'/g, "font-family: '$1'");
  combined = combined.replace(/url\(\.\/files\//g, `url(../vendor/fonts/${dirName}/files/`);
  fs.mkdirSync(path.dirname(destCssPath), { recursive: true });
  fs.writeFileSync(destCssPath, combined);
  copyDir(path.join(familyDir, "files"), destFilesDir);
}

// Variable-font families: ship normal + italic, every subset (unicode-range
// scoped, so browsers only fetch the glyphs actually needed on the page).
const VARIABLE_FONTS = [
  ["@fontsource-variable/inter", "inter", ["index.css", "wght-italic.css"]],
  ["@fontsource-variable/montserrat", "montserrat", ["index.css", "wght-italic.css"]],
  ["@fontsource-variable/source-sans-3", "source-sans-3", ["index.css", "wght-italic.css"]],
  ["@fontsource-variable/outfit", "outfit", ["index.css"]], // Outfit has no italic build
  ["@fontsource-variable/cinzel", "cinzel", ["index.css"]], // Cinzel has no italic build
  ["@fontsource-variable/cormorant-garamond", "cormorant-garamond", ["index.css", "wght-italic.css"]],
  ["@fontsource-variable/playfair-display", "playfair-display", ["index.css", "wght-italic.css"]],
  ["@fontsource-variable/crimson-pro", "crimson-pro", ["index.css", "wght-italic.css"]],
];

for (const [pkg, dirName, cssFiles] of VARIABLE_FONTS) {
  const familyDir = nm(...pkg.split("/"));
  buildFontCss(
    cssFiles.map((f) => path.join(familyDir, f)),
    vendor("fonts", dirName, `${dirName}.css`),
    vendor("fonts", dirName, "files"),
    familyDir,
    dirName
  );
}

// Poppins: no variable build upstream — ship the static weights actually used
// across the site (300/400/500/600/700/800/900, normal style only).
{
  const familyDir = nm("@fontsource", "poppins");
  const weights = ["300", "400", "500", "600", "700", "800", "900"];
  buildFontCss(
    weights.map((w) => path.join(familyDir, `${w}.css`)),
    vendor("fonts", "poppins", "poppins.css"),
    vendor("fonts", "poppins", "files"),
    familyDir,
    "poppins"
  );
}

console.log("Vendored assets written to static/vendor/");
