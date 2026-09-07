#!/usr/bin/env python3
"""Keep Brickwright steering documents small and unambiguous."""

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


def paragraphs(text):
    return {
        re.sub(r"\s+", " ", part).strip().casefold()
        for part in re.split(r"\n\s*\n", text)
        if len(re.sub(r"\s+", " ", part).strip()) >= 80
    }


class SteeringDocsTest(unittest.TestCase):
    def test_plan_contains_only_ordered_pending_work(self):
        plan = (ROOT / "PLAN.md").read_text(encoding="utf-8")
        self.assertNotRegex(plan, r"(?im)^\s*[-*]\s*\[[xX]\]")
        self.assertNotRegex(plan, r"(?im)^#+\s+completed\b|\bcheckpoint log\b")
        tasks = [int(value) for value in re.findall(r"(?m)^(\d+)\. ", plan)]
        self.assertEqual(tasks, list(range(1, len(tasks) + 1)))
        self.assertEqual(plan.count("Acceptance:"), len(tasks))
        self.assertEqual(plan.count("Depends on:"), len(tasks))

    def test_readme_has_unique_headings(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        project_readme = readme.split("## Upstream Renode", 1)[0]
        headings = re.findall(r"(?m)^#{1,6}\s+(.+?)\s*$", project_readme)
        folded = [heading.casefold() for heading in headings]
        self.assertEqual(len(folded), len(set(folded)))

    def test_readme_does_not_repeat_history(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        readme = readme.split("## Upstream Renode", 1)[0]
        history = (ROOT / "HISTORY.md").read_text(encoding="utf-8")
        self.assertFalse(paragraphs(readme) & paragraphs(history))


if __name__ == "__main__":
    unittest.main()
