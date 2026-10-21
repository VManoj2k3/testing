#define CALL(x) ((x) + 1)
int ch20_arg = CALL(
#ifdef NOPE                                    // EXPECT 20.6
1
#else
2
#endif
);
