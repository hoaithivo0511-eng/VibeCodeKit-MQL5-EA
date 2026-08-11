from vibecodekit_mql5.ea_docs_inputs import parse_inputs

MIXED_INPUT_FIXTURE = r'''
input group "Execution";
input double InpRisk = 1.25; // percent risk
sinput int InpRetries = 3;
input string InpEndpoint = "https://host/path;a=1"; // service URL
input double InpRatio = 10.0 / 4.0;
'''


COMMENT_FIXTURE = r'''
// input int IgnoredLine = 1;
/*
input int IgnoredBlock = 2;
sinput bool AlsoIgnored = true;
*/
input group "Live";
input string InpLiteral = "/* not a comment */ // still data"; // literal
/* prefix */ sinput long InpMagic = 123456; /* suffix */
'''


def test_input_and_sinput_are_counted_and_classified_exactly():
    declarations = parse_inputs(MIXED_INPUT_FIXTURE)

    assert len(declarations) == 4
    assert [item.name for item in declarations] == [
        "InpRisk",
        "InpRetries",
        "InpEndpoint",
        "InpRatio",
    ]
    assert [item.storage for item in declarations] == [
        "input",
        "sinput",
        "input",
        "input",
    ]
    assert declarations[0].group == "Execution"
    assert declarations[0].tooltip == "percent risk"
    assert declarations[2].default == '"https://host/path;a=1"'
    assert declarations[3].default == "10.0 / 4.0"


def test_comments_do_not_inflate_exact_input_count():
    declarations = parse_inputs(COMMENT_FIXTURE)

    assert len(declarations) == 2
    assert [item.name for item in declarations] == ["InpLiteral", "InpMagic"]
    assert declarations[0].default == '"/* not a comment */ // still data"'
    assert declarations[0].tooltip == "literal"
    assert declarations[1].storage == "sinput"
    assert declarations[1].line_number == 9


def test_empty_or_non_declaration_source_has_zero_inputs():
    assert parse_inputs("") == []
    assert parse_inputs("int input_like = 1;\ninput group \"Only a group\";") == []


def test_serialized_row_preserves_storage_semantics():
    row = parse_inputs("sinput bool InpEnabled = true;")[0].to_dict()

    assert row["storage"] == "sinput"
    assert row["default"] == "true"
