#include <stdio.h>
#include "ha.h"

void fa(void) {
    printf("fa\n");
}

int main(int argc, char **argv) {
    fa();
    fb();
    return 0;
}