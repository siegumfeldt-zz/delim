import logging 
import unicodedata

from util import *

CR = u'\r'
LF = u'\n'
SPACE = u' '


def mutator(f):
    return f

def handler(f):
    def _f(self, params):
        print f.__name__, params
        return f(self, params)
    return f

logging.basicConfig()

class BacktrackException(Exception):
    def __init__(self, message, params):
        Exception.__init__(self, message)
        (self.charbuffer,
         self.index,
         self.buffer_is_final,
         self.record,
         self.field) = params

    def __str__(self):
        try:
            c = self.charbuffer[self.index]
        except:
            c = '??'
        return "%s (%i+'%s': '%s')" % (self.message, len(self.record), format_string(self.field), format_char(c))


class Parser(object):
    def __init__(self, field_count, delimiter, newline, **kwargs):
        self.log = logging.getLogger(__name__)
        self.allow_unquoted_delimiters_in = set()
        self.allow_unquoted_linebreaks_in = set()
        self.nullstrings = set()
        self.emptystrings = set()

        self.set_delimiter(delimiter)
        self.set_field_count(field_count)
        self.set_newline(newline)

        self.skipinitialspace = False
        self.quoting = False
        self.quotechar = None
        self.minimalquoting = False
        self.unclosedquoting = False
        self.doublequote = False
        self.strict = False
        self.escapechar = None
        self.content_validation_rules = dict()

        self.max_field_length = 1000

    def add_validation_rules(self, field_index, rule):
        field_index = int(field_index)
        if field_index in self.content_validation_rules:
            self.log.warn("Overwriting validation rule for field %i", field_index)
        self.content_validation_rules[field_index] = rule

    def set_delimiter(self, delimiter):
        self.delimiter = get_named_char(delimiter) or unicode(delimiter)
        if len(self.delimiter) != 1:
            raise MetadataException("delimiter must be a one-character unicode string or one of {%s}" % ", ".join(_char_names))

    def set_newline(self, newline):
        if newline.upper() == 'CR' or newline == '\r':
            self.newline = u'MAC' 
        elif newline.upper() == 'LF' or newline == '\n':
            self.newline = u'UNIX' 
        elif newline.upper() == 'CRLF' or newline == '\r\n':
            self.newline = u'DOS'
        else:
            self.newline = unicode(newline).upper()

        if self.newline not in (u"DOS", u"UNIX", u"MAC"):
            raise MetadataException("Newline must be 'UNIX', 'MAC', 'DOS'")  # TODO: Better message needed here 

    def set_field_count(self, field_count):
        self.field_count = int(field_count)

    def set_quotechar(self, quotechar):
        self.quoting = True
        self.quotechar = get_named_char(quotechar) or unicode(quotechar)
        if len(self.quotechar) != 1:
            raise MetadataException("quotechar must be a one-character unicode string or one of {%s}" % ", ".join(_char_names))

    def add_nullstring(self, nullstring):
        self.nullstrings.add(unicode(nullstring))

    def add_emptystring(self, emptystring):
        self.emptystrings.add(unicode(emptystring))

    def set_escapechar(self, escapechar):
        self.escapechar = get_named_char(escapechar) or unicode(escapechar)
        if len(self.escapechar) != 1:
            raise MetadataException("escapechar must be a one-character unicode string or one of {%s}" % ", ".join(_char_names))

    def allow_unquoted_delimiters_in_field(self, i):
        self.allow_unquoted_delimiters_in.add(i)

    def allow_unquoted_linebreaks_in_field(self, i):
        self.allow_unquoted_linebreaks_in.add(i)



########################################################################
########################################################################

    # Mutators
    # Return params, but changed

    @mutator
    def save(self, params, c):
        charbuffer, index, buffer_is_final, record, field = params

        return charbuffer, index+1, buffer_is_final, record, field+c

    @mutator
    def skip(self, params, increment=1):
        charbuffer, index, buffer_is_final, record, field = params
        return charbuffer, index+increment, buffer_is_final, record, field

    @mutator
    def close_field(self, params, last_field=False):
        if not self.can_close_field(params, last_field):
            raise BacktrackException("Can't close", params)

        charbuffer, index, buffer_is_final, record, field = params

        if field in self.nullstrings:
            return (charbuffer, index, buffer_is_final, record+(None,), u'')
        elif field in self.emptystrings:
            return (charbuffer, index, buffer_is_final, record+(u'',), u'')
        else:
            return (charbuffer, index, buffer_is_final, record+(field,), u'')

    @mutator
    def match_string(self, params, s):
        charbuffer, index, buffer_is_final, record, field = params
        for c in s:
            if c != self.get_char(params):
                raise BacktrackException("Failed to match %s" % s, params)
            params = self.skip(params)
        return params

    def can_close_field(self, params, last_field=False):
        charbuffer, index, buffer_is_final, record, field = params
        field_index =len(record)
        field = field
        if field_index in self.content_validation_rules:
            validator = self.content_validation_rules[field_index]
            is_valid = validator(field)
        else:
            is_valid = True
        if last_field:
            return is_valid and len(record)+1 == self.field_count
        else:
            return is_valid and len(record)+1 < self.field_count

    def can_save_unquoted_delimiter(self, params):
        charbuffer, index, buffer_is_final, record, field = params
        return len(record) in self.allow_unquoted_delimiters_in

    def can_save_unquoted_linebreak(self, params):
        charbuffer, index, buffer_is_final, record, field = params
        return len(record) in self.allow_unquoted_linebreaks_in

    def at_eof(self, params, lookahead=0):
        charbuffer, index, buffer_is_final, record, field = params
        if not buffer_is_final:
            return False
        try:
            charbuffer[index+lookahead]
        except IndexError:
            return True
        return False 

    def get_char(self, params, lookahead=0):
        charbuffer, index, buffer_is_final, record, field = params
        try:
            return charbuffer[index+lookahead]
        except IndexError:
            if buffer_is_final:
                raise BacktrackException("Unexpected end of file", params)
            else:
                raise

    def check_field_length(self, params):
        charbuffer, index, buffer_is_final, record, field = params
        if len(field) > self.max_field_length:
            raise BacktrackException("Field too long", params)


    ###########################################################################
    #

    def parse(self, charbuffer, startindex=0, buffer_is_final=True):
        # try:
        params = (charbuffer, startindex, buffer_is_final, (), u'')
        return self.start_field(params)
        # except BacktrackException, e:
            # start_context = max(startindex, e.index-30)
            # end_context = min(len(charbuffer), e.index+5)
            # self.log.critical(e.message)
            # self.log.critical('"%s>>%s"', 
            #     format_string(charbuffer[start_context:e.index]), 
            #     format_string(charbuffer[e.index:end_context]))
            # print "Record:"
            # print format_record(e.record, False)
            # print "Field: '%s'" % format_string(e.field)
            # import traceback
            # import sys
            # exc_type, exc_value, exc_traceback = sys.exc_info()
            # for f, l, func, txt in traceback.extract_tb(exc_traceback):
            #     if func == '_f': continue
            #     print "%s: '%s' (%i)" % (func, txt, l)
            # raise

    @handler
    def start_field(self, params):
        try:
            # get a char
            c = self.get_char(params)
        except BacktrackException:
            if self.strict:
                raise 
            else:
                return self.emit(params)

        if c == SPACE:
            if self.skipinitialspace:
                return self.start_field(self.skip(params))
            else:
                return self.start_field(self.save(params, c))

        elif c == self.quotechar:
            return self.opening_quote(params) # , c)

        else:
            return self.in_unquoted_field(params)

    @handler
    def in_unquoted_field(self, params):
        # Get a char
        try:
            c = self.get_char(params)
        # The backtrack option at EOF is to see if we can emit
        except BacktrackException, e:
            # EOF
            if self.strict:
                raise
            else:
                # if nonstrict, emit
                return self.emit(params)

        if c == self.delimiter:
            # delegate
            return self.delimiter_in_unquoted_field(params)

        elif c == self.escapechar:
            # The next character must be defined, so any IndexError cannot be handled here
            # At EOF, get_char() will raise a BacktrackError
            nextchar = self.get_char(params, 1)
            return self.in_unquoted_field(self.save(self.skip(params), nextchar))

        elif c == LF and self.newline == 'UNIX':
            # delegate
            return self.single_char_linebreak_in_unquoted_field(params)

        elif c == CR:
            if self.newline == 'MAC':
                # delegate
                return self.single_char_linebreak_in_unquoted_field(params)

            if self.newline == 'DOS':
                # delegate
                return self.cr_in_unquoted_field(params)

        else:
            # save and advance
            return self.in_unquoted_field(self.save(params, c))

    @handler
    def delimiter_in_unquoted_field(self, params):
        if self.can_save_unquoted_delimiter(params):
            try:
                c = self.get_char(params)
                return self.in_unquoted_field(self.save(params, c))
            except BacktrackException:
                self.log.debug("Tried saving delimiter but failed", params)
        return self.start_field(self.close_field(self.skip(params)))

    @handler
    def single_char_linebreak_in_unquoted_field(self, params):
        if (not self.at_eof(params, 1) and
            self.can_save_unquoted_linebreak(params)):
            try:
                # so try saving the linebreak (greedy)
                c = self.get_char(params)
                return self.in_unquoted_field(self.save(params, c))
            except BacktrackException, e:
                # didn't work, emit or backtrack
                pass
        return self.emit(self.skip(params))

    @handler
    def cr_in_unquoted_field(self, params):
        # try looking at nextchar
        try:
            nextchar = self.get_char(self.skip(params))
        except BacktrackException:
            # eof after CR, save CR and handle EOF
            return self.in_unquoted_field(self.save(params, c))

        if nextchar == LF:
            # special case: line breaks immediately before eof never get saved
            if (not self.at_eof(params, 2) and 
                self.can_save_unquoted_linebreak(params)):
                # we can save the CRLF
                try:
                    # so try saving CRLF (greedy)
                    return self.in_unquoted_field(self.save(self.skip(params), CR+LF))
                except BacktrackException:
                    # didn't work, emit or backtrack
                    pass
            # we can't save the linebreak
            return self.emit(self.skip(params, 2))

        else:
            # Note that we can't save nextchar now - it might be the delimiter or the escapechar
            return self.in_unquoted_field(self.save(params, c))

    @handler
    def opening_quote(self, params):
        if self.quoting:
            if self.minimalquoting:
                try:
                    return self.in_minimally_quoted_field(self.save(params, c))
                except BacktrackException:
                    # Well, that didn't work
                    pass
            try:
                return self.in_quoted_field(self.skip(params))
            except BacktrackException:
                if self.unclosedquoting:
                    try:
                        return self.in_unclosed_quoted_field(self.skip(params))
                    except BacktrackException:
                        print "giving up on quoting"
                        pass
        c = self.get_char(params)
        return self.in_unquoted_field(self.save(params, c))
            # TODO: warn about quoting seen, but not used

    @handler
    def in_quoted_field(self, params):
        # In a quoted field, we always expect to see more characters,
        # so we can never handle IndexErrors.

        self.check_field_length(params)

        c = self.get_char(params)
        
        if c == self.quotechar:
            return self.quote_in_quoted_field(self.skip(params))

        elif c == self.escapechar:
            # Again, the next character must be defined, so any IndexError 
            # cannot be handled here. If we're at EOF, a BacktrackException
            # will be thrown instead.
            nextchar = self.get_char(params, 1)
            return self.in_quoted_field(self.save(self.skip(params), nextchar))

        else:
            return self.in_quoted_field(self.save(params, c))

    @handler
    def quote_in_quoted_field(self, params):
        try:
            c = self.get_char(params)
        except BacktrackException:
            if self.strict:
                raise
            else:
                return self.emit(params)

        if c == self.delimiter:
            return self.start_field(self.close_field(self.skip(params)))

        elif c == self.quotechar:
            if self.doublequote:
                return self.in_quoted_field(self.save(params, c))
            else:
                raise BacktrackException("Data after closing quote", params)

        elif c == LF and self.newline == 'UNIX':
            return self.emit(self.skip(params)), index+1
        elif c == CR:
            if self.newline == 'MAC':
                return self.emit(self.skip(params)), index+1
            elif self.newline == 'DOS':
                return self.emit(self.match_string(params, CR+LF))
#                nextchar = self.get_char(self.skip(params))
#                if nextchar == LF:
#                    return self.emit(self.skip(params, 2))

            # Not that we can not save nextchar now - it might be the delimiter or the escapechar
            return self.in_unquoted_field(self.save(params, c))

        else:
            raise BacktrackException("Data after closing quote", params)

    @handler
    def in_unclosed_quoted_field(self, params):
        # If we see EOF, we pretend it was preceded by a quote and delegate 
        # to quote_in_quoted_field
        try:
            c = self.get_char(params)
        except BacktrackException:
            return self.quote_in_quoted_field(params)

        if c == self.quotechar:
            raise BacktrackException("Quote seen while trying to parse unclosed quoted field.", params)

        elif c == LF or c == CR or c == self.delimiter:
            try:
                # Pretend we just saw a quote and delegate 
                # to quote_in_quoted_field
                return self.quote_in_quoted_field(params) 
            except BacktrackException:
                # If that fails, save and proceed
                return self.in_unclosed_quoted_field(self.save(params, c))

        elif c == self.escapechar:
            # The next character must be defined, so any IndexError cannot be handled here
            # get_char() will raise a BacktrackException at EOF
            nextchar = self.get_char(self.skip(params))
            return self.in_unclosed_quoted_field(self.save(self.skip(params, 2), nextchar))
        else:
            return self.in_unclosed_quoted_field(self.save(params, c))

    @handler
    def in_minimally_quoted_field(self, params):
        c = self.get_char(params)

        if c==LF or c==CR or c==self.delimiter or c==self.escapechar:
            raise BacktrackException("Non-minimal quoting", params)
        if c == self.quotechar:
            return self.quote_in_quoted_field(self.save(params, c))
        else:
            return self.in_minimally_quoted_field(self.save(params, c))

    @handler
    def emit(self, params):
        charbuffer, index, buffer_is_final, record, field = self.close_field(params, last_field=True)
        return record, index
