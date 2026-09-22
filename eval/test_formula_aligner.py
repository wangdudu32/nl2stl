"""运行：../.venv/bin/python -B -m unittest -v test_formula_aligner.py"""

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from eval import evaluate_file
from formula_aligner import align_formula, load_alignment_rules
from semantic_robustness import SEED
from stl_ast import parse_formula, semantic_key
from stl_metrics_utils import tokenize_formula
from stl_syntax_validator import stl_syntax_validator


class FormulaAlignmentTests(unittest.TestCase):
    def test_every_rule_has_the_same_semantic_key_on_both_sides(self):
        rules = load_alignment_rules()
        self.assertEqual(len(rules), 66)
        for rule in rules:
            with self.subTest(rule=rule.text):
                self.assertEqual(semantic_key(rule.left.root), semantic_key(rule.right.root))

    def test_comparator_is_rewritten_in_gold_style(self):
        result = align_formula("not(x >= 10)", "x < 10")
        self.assertEqual(
            tokenize_formula(result.aligned_pred_stl),
            tokenize_formula("not(x >= 10)"),
        )
        self.assertEqual(len(result.replacements), 1)

    def test_only_equivalent_subtree_is_replaced(self):
        gold = "always(not(x >= 10) and y > 0)"
        pred = "always((x < 10) and y > 1)"
        result = align_formula(gold, pred)
        self.assertIn("not ( x >= 10 )", result.aligned_pred_stl)
        self.assertIn("y > 1", result.aligned_pred_stl)
        self.assertEqual(len(result.replacements), 1)

    def test_commutative_formula_can_be_fully_aligned(self):
        gold = "always((x > 0) and (y < 1))"
        pred = "always((y < 1) and (x > 0))"
        result = align_formula(gold, pred)
        self.assertEqual(tokenize_formula(result.aligned_pred_stl), tokenize_formula(gold))

    def test_temporal_dual_and_edge_dual_are_aligned(self):
        cases = [
            ("eventually[0:5](not(x >= 0))", "not(always[0:5](x >= 0))"),
            ("fall(x >= 0)", "rise(not(x >= 0))"),
        ]
        for gold, pred in cases:
            with self.subTest(gold=gold, pred=pred):
                result = align_formula(gold, pred)
                self.assertEqual(tokenize_formula(result.aligned_pred_stl), tokenize_formula(gold))

    def test_non_equivalent_interval_is_not_replaced(self):
        pred = "always[0:5](x > 0)"
        result = align_formula("always[1:5](x > 0)", pred)
        self.assertEqual(result.aligned_pred_stl, pred)
        self.assertEqual(result.replacements, ())

    def test_alignment_is_valid_semantics_preserving_and_idempotent(self):
        gold = "always(not(x >= 10) and y > 0)"
        pred = "always((x < 10) and y > 1)"
        first = align_formula(gold, pred)
        second = align_formula(gold, first.aligned_pred_stl)
        self.assertTrue(stl_syntax_validator(first.aligned_pred_stl))
        self.assertEqual(
            semantic_key(parse_formula(pred).root),
            semantic_key(parse_formula(first.aligned_pred_stl).root),
        )
        self.assertEqual(second.aligned_pred_stl, first.aligned_pred_stl)
        self.assertEqual(second.replacements, ())

    def test_all_deepstl_2k_formulas_parse(self):
        path = Path(__file__).resolve().parent.parent / "dataset" / "deepstl_test_2k.csv"
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            formulas = [row["STL"] for row in csv.DictReader(file)]
        self.assertEqual(len(formulas), 2000)
        for index, formula in enumerate(formulas):
            with self.subTest(index=index):
                semantic_key(parse_formula(formula).root)

    def test_evaluate_file_uses_alignment_only_for_text_metrics(self):
        record = {"taskid": 7, "gold_stl": "not(x >= 10)", "pred_stl": "x < 10"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text(json.dumps([record]), encoding="utf-8")
            with patch("eval.semantic_scores_for_pair", return_value=(0.25, 0.0)) as semantic:
                with redirect_stdout(io.StringIO()):
                    summary, details = evaluate_file(str(path))

        self.assertEqual(summary["metric_version"], "dsl_eval_v2_alignment")
        self.assertEqual(summary["metrics"]["exact_formula_match"], 1.0)
        self.assertEqual(summary["metrics"]["semantic_robustness"], 0.25)
        self.assertEqual(summary["alignment"]["aligned_sample_count"], 1)
        self.assertEqual(summary["alignment"]["replacement_count"], 1)
        self.assertEqual(
            tokenize_formula(details[0]["aligned_pred_stl"]),
            tokenize_formula(record["gold_stl"]),
        )
        semantic.assert_called_once_with(record["gold_stl"], record["pred_stl"], SEED)


if __name__ == "__main__":
    unittest.main()
