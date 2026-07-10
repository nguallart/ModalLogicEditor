import unittest

from formula_logic import (
    FormulaSyntaxError,
    evaluate_request,
    format_formula,
    parse_evaluation_request,
)
from relation_properties import (
    add_euclidean,
    add_reflexive,
    add_transitive,
    check_dense,
    check_euclidean,
    check_reflexive,
    check_serial,
    check_transitive,
)
from modal_model import (
    ModelParseError,
    World,
    first_free_world,
    normalize_world,
    parse_model,
)


class ModalModelTests(unittest.TestCase):
    def setUp(self):
        self.model = parse_model(
            "w0, w1, w2",
            "(w0,w1), (w1,w2), (w2,w2)",
            "v(p)={w0,w1}\nv(q)={w2}\nv(r)={}",
        )

    def test_world_normalization(self):
        self.assertEqual(normalize_world("w0"), normalize_world("w_0"))
        self.assertEqual(normalize_world("w0"), normalize_world("w_{0}"))
        self.assertEqual(str(normalize_world("w_np")), "w_{np}")

    def test_complete_model(self):
        self.assertEqual(len(self.model.worlds), 3)
        self.assertEqual(len(self.model.relation), 3)
        self.assertEqual(self.model.valuation["r"], frozenset())

    def test_duplicate_world_after_normalization(self):
        with self.assertRaises(ModelParseError):
            parse_model("w0, w_0", "", "")

    def test_first_free_world(self):
        self.assertEqual(
            first_free_world({World("0"), World("1"), World("3")}),
            World("2"),
        )

    def test_atomic_evaluation(self):
        request = parse_evaluation_request("M,w_0 |= p")
        self.assertTrue(evaluate_request(self.model, request))

    def test_box_precedence(self):
        request = parse_evaluation_request("w0 |= []p&q")
        self.assertEqual(format_formula(request.formula), "□p ∧ q")
        self.assertFalse(evaluate_request(self.model, request))

    def test_diamond(self):
        request = parse_evaluation_request("w1 |= <>q")
        self.assertTrue(evaluate_request(self.model, request))

    def test_global_validity(self):
        request = parse_evaluation_request("|= p | ~p")
        self.assertTrue(evaluate_request(self.model, request))

    def test_implication_is_right_associative(self):
        request = parse_evaluation_request("|= p -> q -> r")
        self.assertEqual(format_formula(request.formula), "p → q → r")

    def test_chained_iff_rejected(self):
        with self.assertRaises(FormulaSyntaxError):
            parse_evaluation_request("|= p <-> q <-> r")

    def test_reflexive_check_and_add(self):
        self.assertFalse(check_reflexive(self.model).holds)
        updated = add_reflexive(self.model)
        self.assertTrue(check_reflexive(updated).holds)

    def test_transitive_check_and_add(self):
        self.assertFalse(check_transitive(self.model).holds)
        updated = add_transitive(self.model)
        self.assertTrue(check_transitive(updated).holds)
        self.assertIn((World("0"), World("2")), updated.relation)

    def test_seriality(self):
        self.assertTrue(check_serial(self.model).holds)

    def test_density(self):
        self.assertFalse(check_dense(self.model).holds)

    def test_euclidean_check_and_add(self):
        model = parse_model(
            "w0,w1,w2",
            "(w0,w1),(w0,w2)",
            "",
        )
        self.assertFalse(check_euclidean(model).holds)
        updated = add_euclidean(model)
        self.assertTrue(check_euclidean(updated).holds)
        self.assertIn((World("1"), World("2")), updated.relation)
        self.assertIn((World("2"), World("1")), updated.relation)


if __name__ == "__main__":
    unittest.main()

class ModelFileTests(unittest.TestCase):
    def test_tautology_and_contradiction(self):
        model = parse_model("w0", "", "")
        self.assertTrue(evaluate_request(model, parse_evaluation_request("w0 |= T")))
        self.assertFalse(evaluate_request(model, parse_evaluation_request("w0 |= ~T")))

    def test_duplicate_relations_and_values_are_normalized(self):
        model = parse_model("w0,w1", "(w0,w1),(w0,w1)", "v(p)={w0,w0}")
        self.assertEqual(len(model.relation), 1)
        self.assertEqual(len(model.valuation["p"]), 1)
