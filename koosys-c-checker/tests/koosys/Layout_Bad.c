#include <stdint.h>                            // EXPECT KSYS-DOC-01 EXPECT KSYS-FILE-01
// (no header comment above: purpose/author/date missing)

uint32_t layout_total = 0U;

void Layout_NoDoc(void)                        // EXPECT KSYS-DOC-02 EXPECT KSYS-FUNC-02
{
	layout_total = 1U;                           // EXPECT KSYS-FMT-01
   layout_total = 2U;                          // EXPECT KSYS-FMT-04
    layout_total = layout_total + 1U + 2U + 3U + 4U + 5U + 6U + 7U + 8U; // EXPECT KSYS-FMT-02
}

/** @brief Layout_Long: far longer than one page. */
void Layout_Long(void)                         // EXPECT KSYS-FUNC-01 EXPECT KSYS-FUNC-02
{
    layout_total = layout_total + 0U;
    layout_total = layout_total + 1U;
    layout_total = layout_total + 2U;
    layout_total = layout_total + 3U;
    layout_total = layout_total + 4U;
    layout_total = layout_total + 5U;
    layout_total = layout_total + 6U;
    layout_total = layout_total + 7U;
    layout_total = layout_total + 8U;
    layout_total = layout_total + 9U;
    layout_total = layout_total + 10U;
    layout_total = layout_total + 11U;
    layout_total = layout_total + 12U;
    layout_total = layout_total + 13U;
    layout_total = layout_total + 14U;
    layout_total = layout_total + 15U;
    layout_total = layout_total + 16U;
    layout_total = layout_total + 17U;
    layout_total = layout_total + 18U;
    layout_total = layout_total + 19U;
    layout_total = layout_total + 20U;
    layout_total = layout_total + 21U;
    layout_total = layout_total + 22U;
    layout_total = layout_total + 23U;
    layout_total = layout_total + 24U;
    layout_total = layout_total + 25U;
    layout_total = layout_total + 26U;
    layout_total = layout_total + 27U;
    layout_total = layout_total + 28U;
    layout_total = layout_total + 29U;
    layout_total = layout_total + 30U;
    layout_total = layout_total + 31U;
    layout_total = layout_total + 32U;
    layout_total = layout_total + 33U;
    layout_total = layout_total + 34U;
    layout_total = layout_total + 35U;
    layout_total = layout_total + 36U;
    layout_total = layout_total + 37U;
    layout_total = layout_total + 38U;
    layout_total = layout_total + 39U;
    layout_total = layout_total + 40U;
    layout_total = layout_total + 41U;
    layout_total = layout_total + 42U;
    layout_total = layout_total + 43U;
    layout_total = layout_total + 44U;
    layout_total = layout_total + 45U;
    layout_total = layout_total + 46U;
    layout_total = layout_total + 47U;
    layout_total = layout_total + 48U;
    layout_total = layout_total + 49U;
    layout_total = layout_total + 50U;
    layout_total = layout_total + 51U;
    layout_total = layout_total + 52U;
    layout_total = layout_total + 53U;
    layout_total = layout_total + 54U;
    layout_total = layout_total + 55U;
    layout_total = layout_total + 56U;
    layout_total = layout_total + 57U;
    layout_total = layout_total + 58U;
    layout_total = layout_total + 59U;
    layout_total = layout_total + 60U;
    layout_total = layout_total + 61U;
}
