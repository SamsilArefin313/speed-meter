import unittest

from speed_estimator import SpeedEstimator


class SpeedEstimatorTests(unittest.TestCase):
    def test_times_vehicle_from_a_to_b(self):
        estimator = SpeedEstimator(distance_meters=10.0)
        estimator.update(1, 0, 100, 200, timestamp=0.0)
        at_a = estimator.update(1, 100, 100, 200, timestamp=1.0)
        at_b = estimator.update(1, 200, 100, 200, timestamp=3.0)
        self.assertTrue(at_a.timing)
        self.assertAlmostEqual(at_b.elapsed_seconds, 2.0)
        self.assertAlmostEqual(at_b.speed_kph, 18.0)
        self.assertEqual(at_b.direction, "A -> B")
        self.assertTrue(at_b.completed)

        following_frame = estimator.update(1, 220, 100, 200, timestamp=4.0)
        self.assertFalse(following_frame.completed)

    def test_works_in_reverse_direction(self):
        estimator = SpeedEstimator(distance_meters=20.0)
        estimator.update(1, 250, 100, 200, timestamp=0.0)
        estimator.update(1, 200, 100, 200, timestamp=1.0)
        result = estimator.update(1, 100, 100, 200, timestamp=5.0)
        self.assertAlmostEqual(result.elapsed_seconds, 4.0)
        self.assertAlmostEqual(result.speed_kph, 18.0)
        self.assertEqual(result.direction, "B -> A")
        self.assertTrue(result.completed)

    def test_interpolates_crossing_between_frames(self):
        estimator = SpeedEstimator(distance_meters=10.0)
        estimator.update(1, 50, 100, 200, timestamp=0.0)
        estimator.update(1, 150, 100, 200, timestamp=2.0)
        result = estimator.update(1, 250, 100, 200, timestamp=4.0)
        self.assertAlmostEqual(result.elapsed_seconds, 2.0)


if __name__ == "__main__":
    unittest.main()
