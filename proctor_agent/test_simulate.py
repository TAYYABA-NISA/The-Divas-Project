import unittest

from proctor_agent.__main__ import parse_args
from proctor_agent.simulate import hash_device_identifier, simulated_baseline, simulated_events


class SimulatedAgentTests(unittest.TestCase):
    def test_simulation_has_only_safe_hashed_data(self):
        baseline = simulated_baseline()
        self.assertEqual(len(baseline[0]["device_id_hash"]), 64)
        self.assertNotIn("address", baseline[0])
        for _, _, details in simulated_events():
            self.assertNotIn("face", str(details).lower())
            self.assertNotIn("biometric", str(details).lower())

    def test_cli_requires_explicit_simulation_mode(self):
        args = parse_args(["--server", "http://localhost:8000", "--token", "not-logged", "--simulate"])
        self.assertTrue(args.simulate)
        self.assertEqual(hash_device_identifier("device"), hash_device_identifier("device"))
