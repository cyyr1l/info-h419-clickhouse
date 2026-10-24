/*
 * rowcounts: prints the number of rows that dsdgen generates for each table
 * at a given scale factor, using the kit's own scaling code (scaling.c).
 *
 * Usage: rowcounts -SCALE <sf>
 * Output: one "<table>|<rows>|<kind>" line per table, where kind is
 *   exact   the table has exactly <rows> rows
 *   orders  sales table: <rows> is the number of orders/tickets; each order
 *           has a random number of line items, so the row count is not fixed
 *   child   returns table: generated from the sales rows, no fixed count
 *
 * Built in the tpcds-kit image from the same objects as dsdgen; driver.c is
 * recompiled with -Dmain=dsdgen_main so that this file provides main().
 * Part of the INFO-H-419 project; not part of the TPC kit.
 */
/* Same headers as the kit's driver.c. The option tables of params.h and the
 * other globals come from driver.c itself, compiled with -Dmain=dsdgen_main. */
#include "config.h"
#include "porting.h"
#include <stdio.h>
#include <stdlib.h>
#include "date.h"
#include "decimal.h"
#include "genrand.h"
#include "tdefs.h"
#include "tdef_functions.h"
#include "build_support.h"
#include "params.h"
#include "parallel.h"
#include "tables.h"
#include "release.h"
#include "scaling.h"
#include "error_msg.h"
#include "tpcds.idx.h"

int main(int ac, char **av)
{
    int i;
    tdef *pT;

    process_options(ac, av);
    init_rand();

    for (i = CALL_CENTER; (pT = getSimpleTdefsByNumber(i)); i++) {
        if (!pT->name || i == S_BRAND)
            break;
        if (pT->flags & FL_NOP)
            continue;
        if (pT->flags & FL_CHILD)
            printf("%s|-1|child\n", pT->name);
        else if (pT->flags & FL_PARENT)
            printf("%s|%lld|orders\n", pT->name, (long long)get_rowcount(i));
        else
            printf("%s|%lld|exact\n", pT->name, (long long)get_rowcount(i));
    }
    return 0;
}
