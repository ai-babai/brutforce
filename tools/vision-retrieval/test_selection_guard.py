import copy
import unittest

from selection_guard import filter_composite_candidates


def candidate(box, score):
    return {'box': box, 'score': score, 'prompt': 'a product bottle'}


class CompositeBoxTests(unittest.TestCase):
    def test_low_confidence_scene_box_cannot_beat_two_distinct_bottles(self):
        records = [candidate([0, 0, 100, 100], .15),
                   candidate([10, 0, 35, 100], .9),
                   candidate([60, 0, 85, 100], .8)]
        original = copy.deepcopy(records)
        kept, removed = filter_composite_candidates(records, (100, 100))
        self.assertEqual(kept, records[1:])
        self.assertEqual(removed[0]['child_indices'], [1, 2])
        self.assertEqual(records, original)

    def test_one_bottle_or_overlapping_duplicates_cannot_suppress_full_frame(self):
        for children in ([candidate([5, 5, 95, 95], .9)],
                         [candidate([5, 5, 95, 95], .9),
                          candidate([6, 6, 94, 94], .8)]):
            records = [candidate([0, 0, 100, 100], .1)] + children
            self.assertEqual(filter_composite_candidates(records, (100, 100)), (records, []))

    def test_low_score_or_not_contained_children_do_not_remove_candidate(self):
        for score, box in ((.49, [60, 0, 85, 100]), (.8, [90, 0, 130, 100])):
            records = [candidate([0, 0, 100, 100], .15),
                       candidate([10, 0, 35, 100], .9), candidate(box, score)]
            self.assertEqual(filter_composite_candidates(records, (150, 100)), (records, []))

    def test_confident_parent_is_retained(self):
        records = [candidate([0, 0, 100, 100], .6),
                   candidate([10, 0, 35, 100], .9), candidate([60, 0, 85, 100], .8)]
        self.assertEqual(filter_composite_candidates(records, (100, 100)), (records, []))

    def test_invalid_geometry_is_an_error(self):
        with self.assertRaises(ValueError):
            filter_composite_candidates([candidate([1, 1, 1, 2], .9)], (100, 100))


if __name__ == '__main__':
    unittest.main()
