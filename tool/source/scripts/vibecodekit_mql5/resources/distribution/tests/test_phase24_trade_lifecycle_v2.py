from pathlib import Path

from vibecodekit_mql5.advanced_codegen import generate
from vibecodekit_mql5.build_planner import plan

from tests.test_phase17_runtime_safety import base_ir


def generated_runtime(tmp_path: Path):
    ir = base_ir()
    ir.strategy["parameters"]["async_execution"] = True
    build = plan(ir)
    assert build.ok, build.blockers
    out = generate(ir, build, tmp_path / "intent-v2")
    return (
        (out / "Include/RuntimeSafeEA/Core/TradeIntentLedger.mqh").read_text(
            encoding="utf-8"
        ),
        (out / "Include/RuntimeSafeEA/Core/AsyncTradeExecutor.mqh").read_text(
            encoding="utf-8"
        ),
        (out / "Experts/RuntimeSafeEA/RuntimeSafeEA.mq5").read_text(
            encoding="utf-8"
        ),
    )


def test_intent_v2_uses_request_order_position_and_deal_identity(tmp_path: Path):
    ledger, executor, _ = generated_runtime(tmp_path)

    request_at = ledger.index("FindByRequest(request_id")
    order_at = ledger.index("FindByOrder(order")
    position_at = ledger.index("FindByPosition(trans.position")
    assert request_at < order_at < position_at
    assert 'SaveUlong(source,direction,"order"' in ledger
    assert 'SaveUlong(source,direction,"position"' in ledger
    assert 'SaveUlong(source,direction,"deal"' in ledger
    assert "result.request_id" in ledger
    assert "result.order" in ledger
    assert "result.deal" in ledger
    assert "m_trade.Result(submit_result)" in executor
    assert "request_event=trans.type==TRADE_TRANSACTION_REQUEST" in ledger


def test_broker_comment_is_diagnostic_and_never_authority(tmp_path: Path):
    ledger, executor, _ = generated_runtime(tmp_path)

    assert "LegacyCommentMatches" in ledger  # RC4 migration bootstrap only
    assert "CommentHas" not in ledger
    assert "FindLive" not in ledger
    diagnostic_start = ledger.index("void ObserveDiagnosticComment")
    transaction_start = ledger.index("bool OnTransaction", diagnostic_start)
    diagnostic_body = ledger[diagnostic_start:transaction_start]
    assert "diag_seen" in diagnostic_body
    assert "Clear(" not in diagnostic_body
    transaction_body = ledger[transaction_start:ledger.index("void Reconcile", transaction_start)]
    assert "LegacyCommentMatches" not in transaction_body
    assert "m_intents.OnTransaction(trans,result)" in executor
    assert "ObserveDiagnosticComment" in executor


def test_submission_partial_and_completion_are_distinct_states(tmp_path: Path):
    ledger, executor, _ = generated_runtime(tmp_path)

    for state in (
        "VCK_INTENT_CREATED",
        "VCK_INTENT_PREPARED",
        "VCK_INTENT_SUBMITTED",
        "VCK_INTENT_ACKNOWLEDGED",
        "VCK_INTENT_PARTIAL",
        "VCK_INTENT_FILLED",
        "VCK_INTENT_COMPLETED",
        "VCK_INTENT_UNKNOWN",
        "VCK_INTENT_REJECTED",
        "VCK_INTENT_OPERATOR_REQUIRED",
    ):
        assert state in ledger
    assert "TRADE_RETCODE_DONE_PARTIAL)SetState" in ledger
    assert "TRADE_TRANSACTION_DEAL_ADD" in ledger
    deal_add_start = ledger.index("if(trans.type==TRADE_TRANSACTION_DEAL_ADD")
    deal_add = ledger[
        deal_add_start : ledger.index(
            "if(request_event&&result.retcode==TRADE_RETCODE_PLACED",
            deal_add_start,
        )
    ]
    assert "SetState(source,direction,VCK_INTENT_PARTIAL)" in deal_add
    assert "Clear(" not in deal_add
    assert "HistoryDealForOrder(order)||HistoryDealIdentity(deal)" in ledger
    assert "m_intents.MarkSubmitted" in executor
    assert "m_intents.MarkUnknown" in executor


def test_operation_specific_retcode_policies_are_not_collapsed(tmp_path: Path):
    _, executor, _ = generated_runtime(tmp_path)

    assert "OpenRetcodeAccepted" in executor
    assert "ModifyRetcodeAccepted" in executor
    assert "CloseRetcodeAccepted" in executor
    assert "DeleteRetcodeAccepted" in executor
    assert "GoodRetcode" not in executor
    modify = executor[
        executor.index("bool ModifyRetcodeAccepted") : executor.index(
            "bool CloseRetcodeAccepted"
        )
    ]
    delete = executor[
        executor.index("bool DeleteRetcodeAccepted") : executor.index(
            "bool OpenDefinitelyRejected"
        )
    ]
    assert "TRADE_RETCODE_NO_CHANGES" in modify
    assert "TRADE_RETCODE_NO_CHANGES" not in delete
    assert "TransactionRetcodeAccepted" in executor


def test_intent_and_state_flushes_are_bound_to_critical_boundaries(tmp_path: Path):
    ledger, _, main = generated_runtime(tmp_path)

    assert "GlobalVariablesFlush" in ledger
    assert "void PersistStateCritical(){PersistState();GlobalVariablesFlush();}" in main
    assert "bool ApplyTradeDeal" in main
    assert "bool ProcessPendingTradeEvents" in main
    assert "void ProcessAndPersistPendingTradeEvents" in main
    assert "ProcessAndPersistPendingTradeEvents();" in main
    transaction = main[main.index("void OnTradeTransaction") :]
    assert "if(critical)PersistStateCritical()" in transaction
    assert "PersistState();" not in transaction
    assert "trans.type==TRADE_TRANSACTION_REQUEST" in transaction
    assert "TransactionRetcodeAccepted(request.action,result.retcode)" in transaction


def test_unknown_submission_stays_sealed_until_identity_reconciliation(
    tmp_path: Path,
):
    ledger, executor, _ = generated_runtime(tmp_path)

    assert "VCK_INTENT_OPERATOR_REQUIRED" in ledger
    prepare = ledger[ledger.index("bool Prepare"):ledger.index("void MarkSubmitted")]
    assert "MigrateLegacySlot(source,direction)" in prepare
    assert "m_intents.MarkUnknown(source,direction,submit_result)" in executor
    assert "retry_after_timeout" not in ledger
    assert "HistoryDealForOrder(order)" in ledger


def test_rc4_intent_namespace_is_dual_read_and_single_write_v2(tmp_path: Path):
    ledger, _, _ = generated_runtime(tmp_path)

    assert 'm_prefix="VCK_INTENT_V2_"' in ledger
    assert 'm_v1_prefix="VCK_INTENT_"' in ledger
    assert "LegacyKey" in ledger
    assert "MigrateLegacySlot" in ledger
    assert "MigrateLegacy();" in ledger
    prepare = ledger[ledger.index("bool Prepare"):ledger.index("void MarkSubmitted")]
    assert "MigrateLegacySlot(source,direction)" in prepare
    assert 'GlobalVariableSet(Key(source,direction,"legacy_migrated"),1.0)' in ledger
    assert "VCK_INTENT_UNKNOWN" in ledger
    # New submissions only write Key(...), never LegacyKey(...).
    new_write = prepare[prepare.index("long id=MakeId"):]
    assert "LegacyKey" not in new_write


def test_migrated_v1_state_is_preserved_until_terminal_or_operator_clear(tmp_path: Path):
    ledger, _, _ = generated_runtime(tmp_path)

    migrate = ledger[ledger.index("bool MigrateLegacySlot"):ledger.index("void MigrateLegacy()")]
    assert "ClearLegacy" not in migrate
    assert "if(terminal)" in migrate
    clear = ledger[ledger.index("void Clear("):ledger.index("bool FindByRequest")]
    assert "if(migrated)ClearLegacy" in clear
    reconcile = ledger[ledger.index("bool ReconcileSlot"):ledger.index("public:")]
    escalation = ledger[
        ledger.index("void EscalateExpiredIntent"):ledger.index("bool ReconcileSlot")
    ]
    assert "EscalateExpiredIntent(source,direction)" in reconcile
    assert "VCK_INTENT_OPERATOR_REQUIRED" in escalation
    assert "TimeCurrent()-created>=m_timeout" in escalation
    assert "Clear(source,direction)" not in escalation[escalation.index("VCK_INTENT_OPERATOR_REQUIRED"):]


def test_operator_clear_records_durable_audit_before_removal(tmp_path: Path):
    ledger, _, _ = generated_runtime(tmp_path)

    operator = ledger[ledger.index("bool OperatorClear"):ledger.index("void ObserveDiagnosticComment")]
    assert 'AuditKey(id,"operator_clear_at")' in operator
    assert 'AuditKey(id,"operator_clear_code")' in operator
    assert operator.index("GlobalVariablesFlush") < operator.index("Clear(source,direction)")


def test_v2_state_numbers_remain_compatible_while_new_terminal_states_append(tmp_path: Path):
    ledger, _, _ = generated_runtime(tmp_path)

    enum_line = next(line for line in ledger.splitlines() if line.startswith("enum VCKTradeIntentState"))
    assert "VCK_INTENT_NONE=0,VCK_INTENT_PREPARED,VCK_INTENT_SUBMITTED" in enum_line
    assert "VCK_INTENT_COMPLETED,VCK_INTENT_UNKNOWN,VCK_INTENT_REJECTED,VCK_INTENT_OPERATOR_REQUIRED" in enum_line
    assert "const VCKTradeIntentState VCK_INTENT_CREATED=VCK_INTENT_PREPARED;" in ledger
    assert "const VCKTradeIntentState VCK_INTENT_FILLED=VCK_INTENT_COMPLETED;" in ledger
