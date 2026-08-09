from pathlib import Path

from vibecodekit_mql5.lint_best_practice import detect_ap16, detect_ap24
from vibecodekit_mql5.lint_ui import detect_ui_perf03, detect_ux10
from vibecodekit_mql5.modernize import analyze_modernization


def test_stdlib_ctrade_wrapper_is_not_reinvent_stdlib():
    src = '#include <Trade/Trade.mqh>\nclass CAsyncTradeExecutor { CTrade m_trade; };'
    assert detect_ap16('x.mqh', src, src) == []


def test_indicator_handle_init_plus_barscalculated_is_synchronized():
    src = 'int h=iMA(_Symbol,PERIOD_H1,20,0,MODE_EMA,PRICE_CLOSE); bool V(){return BarsCalculated(h)>2&&CopyBuffer(h,0,1,1,a)==1;}'
    assert detect_ap24('x.mqh', src, src) == []


def test_itime_zero_sentinel_is_a_guard():
    src = 'bool NewBar(){datetime t=iTime(_Symbol,PERIOD_H1,0);if(t==0)return false;return true;}'
    assert detect_ap24('x.mq5', src, src) == []


def test_resource_owner_release_method_is_accepted():
    src = 'class E{ int h; bool Init(){h=iCustom(_Symbol,PERIOD_H1,"x");return true;} void Release(){IndicatorRelease(h);} };'
    assert detect_ui_perf03('x.mqh', src, src) == []


def test_ux10_does_not_span_multiple_literals():
    raw = 'if(h!=INVALID_HANDLE){FileWrite(h,"mfe",DoubleToString(x,2));GlobalVariableDel(Key(id,"mfe"));}'
    assert detect_ux10('x.mqh', raw, raw) == []


def test_current_mql5_pending_order_apis_are_not_legacy():
    src = 'for(int i=OrdersTotal()-1;i>=0;i--){ulong t=OrderGetTicket(i);if(t>0&&OrderSelect(t)){} }'
    titles = {x['title'] for x in analyze_modernization(src)['issues']}
    assert 'MQL4-style OrderSelect()' not in titles
    assert 'MQL4 order API' not in titles

from vibecodekit_mql5.ea_ir import from_dict
from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.advanced_codegen import generate


def test_generated_ontick_is_an_orchestrator_not_a_monolith(tmp_path: Path):
    ir = from_dict({
        'schema_version':'3.1',
        'identity':{'name':'AuditEA','version':'1.0'},
        'runtime':{'account_model':'hedging','symbols':['EURUSD'],'timeframes':['H1']},
        'requirements':[
            {'id':'R1','path':'strategy.entry.signals.rsi','value':True,'priority':'must','status':'confirmed','confidence':1.0,'source_refs':[]},
            {'id':'R2','path':'strategy.dca.enabled','value':True,'priority':'must','status':'confirmed','confidence':1.0,'source_refs':[]},
        ],
        'strategy':{'parameters':{'signal_mode':'rsi','dca_mode':'step','lot_mode':'multiply'}},
        'risk':{'max_lot':1.0},
    })
    out = tmp_path/'p'
    generate(ir,plan(ir),out)
    main=(out/'Experts/AuditEA/AuditEA.mq5').read_text()
    assert 'bool TickAdmissionGate()' in main
    assert 'bool RiskMutationGate(' in main
    assert 'bool ExitMutationChain(' in main
    assert 'bool ExposureMutationChain(' in main
    body=main.split('void OnTick()',1)[1].split('void OnTradeTransaction',1)[0]
    assert body.count('if(') <= 5

from vibecodekit_mql5.check_all import _stage_stress


def test_check_all_stress_stage_is_read_only(tmp_path: Path):
    project = tmp_path/'project'
    report = project/'evidence/stress/stress-matrix-report.json'
    report.parent.mkdir(parents=True)
    original = '{"counts":{"PASS":0,"FAIL":0,"SKIPPED":0,"UNTESTABLE":8}}\n'
    report.write_text(original)
    before = report.read_bytes()
    stage = _stage_stress(project)
    assert stage.status == 'UNTESTABLE'
    assert report.read_bytes() == before


def test_secondary_dca_mode_switch_is_generated(tmp_path: Path):
    ir = from_dict({
        'schema_version':'3.1',
        'identity':{'name':'SwitchEA','version':'1.0'},
        'runtime':{'account_model':'hedging','symbols':['EURUSD'],'timeframes':['H1']},
        'requirements':[
            {'id':'R1','path':'strategy.entry.signals.rsi','value':True,'priority':'must','status':'confirmed','confidence':1.0,'source_refs':[]},
            {'id':'R2','path':'strategy.dca.enabled','value':True,'priority':'must','status':'confirmed','confidence':1.0,'source_refs':[]},
            {'id':'R3','path':'strategy.dca.step_multiplier','value':True,'priority':'must','status':'confirmed','confidence':1.0,'source_refs':[]},
            {'id':'R4','path':'strategy.dca.signal','value':True,'priority':'must','status':'confirmed','confidence':1.0,'source_refs':[]},
        ],
        'strategy':{'parameters':{'signal_mode':'rsi','dca_mode':'step_multiplier','dca_switch_count':10,'dca_secondary_mode':'signal','lot_mode':'multiply'}},
        'risk':{'max_lot':1.0},
    })
    out=tmp_path/'switch'
    generate(ir,plan(ir),out)
    cfg=(out/'Include/SwitchEA/Config.mqh').read_text()
    main=(out/'Experts/SwitchEA/SwitchEA.mq5').read_text()
    assert 'InpDCASwitchCount=10' in cfg
    assert 'InpDCASecondaryMode=VCK_DCA_SIGNAL' in cfg
    assert 'VCKDCAMode ActiveDCAMode(const int count)' in main
    assert 'switch(mode)' in main
