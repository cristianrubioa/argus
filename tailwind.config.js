module.exports = {
  // router.py builds some markup (the release-notes excerpt) in Python, not a template — scanned
  // too, so a class used only there still gets compiled.
  content: ["./src/argus/web/templates/**/*.html", "./src/argus/web/router.py"],
  darkMode: "class",
};
