#!/usr/bin/python

import unittest

from delim.parser import Parser, BacktrackException


class TestUnquoted(unittest.TestCase):
    def setUp(self):
        self.parser = Parser(3, u';', 'UNIX')

    def tearDown(self):
        del self.parser

    def _test(self, buf, record):
        result_record, result_charcount = self.parser.parse(buf, 0, False)
        self.assertEqual(result_record, record)
        self.assertEqual(result_charcount, len(buf))

    def _test_as_final(self, buf, record):
        result_record, result_charcount = self.parser.parse(buf, 0, True)
        self.assertEqual(result_record, record)
        self.assertEqual(result_charcount, len(buf))

    def _test_fails(self, buf):
        self.assertRaises(BacktrackException, self.parser.parse, buf, 0, False)

    def _test_fails_as_final(self, buf):
        self.assertRaises(BacktrackException, self.parser.parse, buf, 0, True)

    def _test_needsmore(self, buf):
        self.assertRaises(IndexError, self.parser.parse, buf, 0, False)

    def test_too_short_record_fails(self):
        self._test_fails(u"a;b\n")

    def test_too_short_record_fails_as_final(self):
        self._test_fails_as_final(u"a;b")

    def test_too_short_record_needs_more(self):
        self._test_needsmore(u"a;b")

    def test_basic(self):
        self._test(u"ab;cd;ef\n", (u"ab", u"cd", u"ef"))

    def test_basic_with_dead_quoting(self):
        self._test(u'"ab";cd;ef\n', (u'"ab"', u"cd", u"ef"))

    def test_partial_quoting(self):
        self._test(u'"ab"ba;cd;ef\n', (u'"ab"ba', u"cd", u"ef"))

    def test_basic_with_dead_escape(self):
        self._test(u'a\\b;cd;ef\n', (u'a\\b', u"cd", u"ef"))

    def test_escapes_are_dead_by_default(self):
        self._test_fails(u"ab;c\\;d;ef\n")

    def test_escaped_delimiter(self):
        self.parser.set_escapechar('BACKSLASH')
        self._test(u"ab;c\\;d;ef\n", (u"ab", u"c;d", u"ef"))

    def test_escaped_newline(self):
        self.parser.set_escapechar('BACKSLASH')
        self._test(u"ab;c\\\nd;ef\n", (u"ab", u"c\nd", u"ef"))

    def test_spare_delimiter_in_first_field(self):
        self.parser.allow_unquoted_delimiters_in_field(0)
        self._test("a;b;cd;ef\n", (u"a;b", u"cd", u"ef"))

    def test_spare_delimiter_in_last_field(self):
        self.parser.allow_unquoted_delimiters_in_field(2)
        self._test("ab;cd;e;f\n", (u"ab", u"cd", u"e;f"))

    def test_spare_linebreak_in_first_field(self):
        self.parser.allow_unquoted_linebreaks_in_field(0)
        self._test("a\nb;cd;ef\n", (u"a\nb", u"cd", u"ef"))


    def test_strict_fails_on_missing_linebreak(self):
        self.parser.strict = True
        self._test_fails_as_final(u"a;b;c")

class TestQuoted(unittest.TestCase):
    def setUp(self):
        self.parser = Parser(3, u';', 'UNIX')
        self.parser.quoting = True
        self.parser.set_quotechar(u'"')

    def _test(self, buf, record):
        result_record, result_charcount = self.parser.parse(buf, 0, False)
        self.assertEqual(result_record, record)
        self.assertEqual(result_charcount, len(buf))

    def test_basic(self):
        self._test(u'"ab";cd;ef\n', (u"ab", u"cd", u"ef"))

    def test_partial_quoting(self):
        self._test(u'"ab"ba;cd;ef\n', (u'"ab"ba', u"cd", u"ef"))


    def test_unclosed(self):
        self.parser.max_field_length = 2
        self.parser.unclosedquoting = True
        self._test(u'"aaaa;cd;ef\n', (u"aaaa", u"cd", u"ef"))

if __name__=="__main__":
    unittest.main()
