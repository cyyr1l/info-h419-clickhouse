-- Toy Batch1 data. Expected counts are checked by run_tests.sh.
INSERT INTO DimBroker   VALUES (1), (2);
INSERT INTO DimAccount  VALUES (10, 1), (11, 2), (12, 99);          -- account 12 points to a missing broker
INSERT INTO DimCustomer VALUES (100, 1, 'Active'), (101, 1, 'Inactive'), (102, 0, 'Inactive');
INSERT INTO DimDate     VALUES (20170707), (20170708);
INSERT INTO DimTime     VALUES (0), (1);
INSERT INTO DimCompany  VALUES (500);
INSERT INTO DimSecurity VALUES (700), (701);
INSERT INTO DimTrade    VALUES (1, 'SBMT'), (2, 'SBMT');
INSERT INTO DimTrade    VALUES (1, 'CMPT');                          -- new version of trade 1: FINAL must count 2, not 3
INSERT INTO FactCashBalances VALUES (10, 100, 20170707), (12, 100, 20170707);   -- joined: 1
INSERT INTO FactHoldings VALUES (10, 100, 20170707, 0, 500, 700), (11, 101, 20170708, 1, 500, 999); -- joined: 1
INSERT INTO FactMarketHistory VALUES (20170707, 500, 700), (20170707, 500, 701), (20170707, 501, 700); -- joined: 2
INSERT INTO FactWatches VALUES (100, 700, 20170707, NULL), (101, 701, 20170707, 20170708), (999, 700, 20170707, NULL); -- joined: 2, inactive: 1
INSERT INTO Financial   VALUES (500);
INSERT INTO Industry    VALUES ('AM'), ('AP');
INSERT INTO Prospect    VALUES ('A1');
INSERT INTO StatusType  VALUES ('ACTV');
INSERT INTO TaxRate     VALUES ('US1');
INSERT INTO TradeType   VALUES ('TMB');
