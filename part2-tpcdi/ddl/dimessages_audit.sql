-- DImessages and Audit tables (TPC-DI spec).
-- Column names match the spec exactly so the audit queries (Appendix A-C) run unchanged.
-- Owner: role 4 (cluster D).

-- DImessages: log written by the ETL (status, alerts, validation counts, phase-complete records).
-- Spec types: MessageDateAndTime TIMESTAMP NOT NULL, BatchID NUM(5) NOT NULL,
--             MessageSource CHAR(30), MessageText CHAR(50) NOT NULL,
--             MessageType CHAR(12) NOT NULL, MessageData CHAR(100).
-- Notes:
--   * DateTime64(3): the spec needs 0.1 s precision, fill it with now64(3), never CURRENT_TIMESTAMP.
--   * BatchID is UInt32 (group type rule). The audit computes BatchID - 1:
--     in ClickHouse unsigned minus unsigned returns Int64, so 0 - 1 = -1 (no wrap-around).
--   * MessageSource and MessageData are Nullable: the PCR record has MessageData = NULL.
CREATE TABLE IF NOT EXISTS DImessages
(
    MessageDateAndTime DateTime64(3),
    BatchID            UInt32,
    MessageSource      Nullable(String),
    MessageText        String,
    MessageType        String,
    MessageData        Nullable(String)
)
ENGINE = MergeTree
ORDER BY (BatchID, MessageType, MessageDateAndTime);

-- Audit: expected values produced by DIGen, loaded from every *_audit.csv
-- (Batch1_audit.csv ... Generator_audit.csv in the root, Batch*/<Source>_audit.csv).
-- Spec types: DataSet CHAR(20) NOT NULL, BatchID NUM(5), Date DATE,
--             Attribute CHAR(50) NOT NULL, Value NUM(15), DValue NUM(15,5).
CREATE TABLE IF NOT EXISTS Audit
(
    DataSet   String,
    BatchID   Nullable(UInt32),
    Date      Nullable(Date32),  -- Date32, not Date: Date starts in 1970 and Batch1 FirstDay is 1950-01-01
    Attribute String,
    Value     Nullable(Decimal(15, 0)),
    DValue    Nullable(Decimal(18, 5))   -- not (15, 5): DIGen writes ONE_YEAR_IN_MILLISECONDS = 31557600000 (11 integer digits)
)
ENGINE = MergeTree
ORDER BY (DataSet, Attribute);
