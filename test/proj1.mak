
CC = cc
CFLAGS = -O2

all: fa fb

FA_OBJS = fa.o fb.o fc.o
FB_OBJS = fa.o fb.o

fa: $(FA_OBJS)
	$(CC) $(FA_OBJS) -o $@

fb: $(FB_OBJS)
	$(CC) $(FB_OBJS) -o $@

.c.o:
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f fa fb *.o

