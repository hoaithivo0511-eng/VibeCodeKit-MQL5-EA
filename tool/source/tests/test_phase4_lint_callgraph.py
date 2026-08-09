from vibecodekit_mql5.lint_best_practice import detect_ap22


def test_ap22_accepts_executor_open_call_reached_from_ontick():
    src = '''
void ManageEntry(){ Trade.Open(1,_Symbol,0.01,1.0,0,0,"x"); }
void OnTick(){ ManageEntry(); }
'''
    assert detect_ap22("ea.mq5", src, src) == []


def test_ap22_still_flags_true_placeholder():
    src = 'void OnTick(){ int x=1; if(x>0) Print(x); }'
    findings = detect_ap22("ea.mq5", src, src)
    assert findings and findings[0].code == "AP-22"
