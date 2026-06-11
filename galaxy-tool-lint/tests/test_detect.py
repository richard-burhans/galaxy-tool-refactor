import unittest
from galaxy_tool_lint import detect
from galaxy_tool_source import binding

class TestDetectViolationsNoMutation(unittest.TestCase):
    def test_detect_violations_no_mutation(self):
        tool_xml = b"<tool><id>test</id></tool>"
        tool = binding.load_tool(tool_xml)
        original_tool_bytes = tool.to_xml().encode('utf-8')

        detect_violations_result = detect.detect_violations(tool)

        mutated_tool_bytes = tool.to_xml().encode('utf-8')
        self.assertEqual(original_tool_bytes, mutated_tool_bytes)

if __name__ == '__main__':
    unittest.main()