/*
 * heat1d - explicit finite-difference solver for the 1D heat equation
 *
 *     u_t = alpha * u_xx   on [0, 1],   u(0,t) = u(1,t) = 0,   u(x,0) = sin(pi x)
 *
 * Exact solution: u(x,t) = exp(-alpha * pi^2 * t) * sin(pi * x)
 *
 * The scheme (FTCS) is only stable if dt <= dx^2 / (2 * alpha); larger time
 * steps are rejected instead of silently producing garbage.
 *
 * Exit codes: 0 = success, 1 = invalid arguments or I/O error, 2 = unstable dt.
 */
#define _POSIX_C_SOURCE 200809L
#ifdef __APPLE__
#define _DARWIN_C_SOURCE
#endif

#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _OPENMP
#include <omp.h>
#endif

#define PI 3.14159265358979323846
#define MAX_POINTS 10000000L
#define MAX_STEPS 1.0e10

enum { RC_OK = 0, RC_USAGE = 1, RC_UNSTABLE = 2 };

struct params {
    long nx;            /* number of grid points, including both boundaries */
    double alpha;       /* diffusivity */
    double dt;          /* time step, 0 = choose automatically */
    double tmax;        /* final time */
    const char *out;    /* output path, "-" = stdout */
};

static void usage(FILE *stream)
{
    fprintf(stream,
            "usage: heat1d [--nx N] [--alpha A] [--dt DT] [--tmax T] [--out FILE]\n"
            "  --nx N      grid points, >= 3        (default 101)\n"
            "  --alpha A   diffusivity, > 0         (default 1.0)\n"
            "  --dt DT     time step, 0 = automatic (default 0)\n"
            "  --tmax T    final time, > 0          (default 0.1)\n"
            "  --out FILE  CSV output, '-' = stdout (default -)\n");
}

static int parse_long(const char *s, long *out)
{
    char *end = NULL;

    errno = 0;
    long v = strtol(s, &end, 10);
    if (errno != 0 || end == s || *end != '\0') {
        return -1;
    }
    *out = v;
    return 0;
}

static int parse_double(const char *s, double *out)
{
    char *end = NULL;

    errno = 0;
    double v = strtod(s, &end);
    if (errno != 0 || end == s || *end != '\0' || !isfinite(v)) {
        return -1;
    }
    *out = v;
    return 0;
}

/* Returns 0 on success, 1 if --help was requested, -1 on error. */
static int parse_args(int argc, char **argv, struct params *p)
{
    for (int i = 1; i < argc; i++) {
        const char *opt = argv[i];

        if (strcmp(opt, "--help") == 0 || strcmp(opt, "-h") == 0) {
            return 1;
        }
        if (i + 1 >= argc) {
            fprintf(stderr, "heat1d: option '%s' needs a value\n", opt);
            return -1;
        }
        const char *val = argv[++i];
        int rc = -1;

        if (strcmp(opt, "--nx") == 0) {
            rc = parse_long(val, &p->nx);
        } else if (strcmp(opt, "--alpha") == 0) {
            rc = parse_double(val, &p->alpha);
        } else if (strcmp(opt, "--dt") == 0) {
            rc = parse_double(val, &p->dt);
        } else if (strcmp(opt, "--tmax") == 0) {
            rc = parse_double(val, &p->tmax);
        } else if (strcmp(opt, "--out") == 0) {
            p->out = val;
            rc = 0;
        } else {
            fprintf(stderr, "heat1d: unknown option '%s'\n", opt);
            return -1;
        }
        if (rc != 0) {
            fprintf(stderr, "heat1d: invalid value '%s' for option '%s'\n", val, opt);
            return -1;
        }
    }
    return 0;
}

static int write_csv(const char *path, const double *u, long nx)
{
    FILE *f = (strcmp(path, "-") == 0) ? stdout : fopen(path, "w");

    if (f == NULL) {
        fprintf(stderr, "heat1d: cannot open '%s': %s\n", path, strerror(errno));
        return -1;
    }
    fprintf(f, "x,u\n");
    for (long i = 0; i < nx; i++) {
        fprintf(f, "%.12e,%.12e\n", (double)i / (double)(nx - 1), u[i]);
    }
    if (f == stdout) {
        return fflush(f) == 0 ? 0 : -1;
    }
    return fclose(f) == 0 ? 0 : -1;
}

int main(int argc, char **argv)
{
    struct params p = {.nx = 101, .alpha = 1.0, .dt = 0.0, .tmax = 0.1, .out = "-"};

    int parsed = parse_args(argc, argv, &p);
    if (parsed == 1) {
        usage(stdout);
        return RC_OK;
    }
    if (parsed < 0) {
        usage(stderr);
        return RC_USAGE;
    }
    if (p.nx < 3 || p.nx > MAX_POINTS || p.alpha <= 0.0 || p.tmax <= 0.0 || p.dt < 0.0) {
        fprintf(stderr,
                "heat1d: invalid parameters (need 3 <= nx <= %ld, alpha > 0, tmax > 0, dt >= 0)\n",
                MAX_POINTS);
        return RC_USAGE;
    }

    const double dx = 1.0 / (double)(p.nx - 1);
    const double dt_limit = dx * dx / (2.0 * p.alpha);
    double dt = p.dt;

    if (dt == 0.0) {
        dt = 0.4 * dx * dx / p.alpha; /* 80 % of the stability limit */
    } else if (dt > dt_limit) {
        fprintf(stderr, "heat1d: unstable time step: dt=%.6g exceeds dx^2/(2*alpha)=%.6g\n", dt,
                dt_limit);
        return RC_UNSTABLE;
    }

    const double steps_f = ceil(p.tmax / dt);
    if (steps_f > MAX_STEPS) {
        fprintf(stderr, "heat1d: too many time steps (%.3g)\n", steps_f);
        return RC_USAGE;
    }
    const long steps = (long)steps_f;
    dt = p.tmax / (double)steps; /* hit tmax exactly; dt only gets smaller, so still stable */
    const double r = p.alpha * dt / (dx * dx);

    double *u = calloc((size_t)p.nx, sizeof *u);
    double *un = calloc((size_t)p.nx, sizeof *un);
    if (u == NULL || un == NULL) {
        fprintf(stderr, "heat1d: out of memory\n");
        free(u);
        free(un);
        return RC_USAGE;
    }
    for (long i = 1; i < p.nx - 1; i++) {
        u[i] = sin(PI * (double)i * dx);
    }

    int threads = 1;
#ifdef _OPENMP
    threads = omp_get_max_threads();
#endif

    struct timespec t0;
    struct timespec t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    for (long n = 0; n < steps; n++) {
#ifdef _OPENMP
#pragma omp parallel for
#endif
        for (long i = 1; i < p.nx - 1; i++) {
            un[i] = u[i] + r * (u[i - 1] - 2.0 * u[i] + u[i + 1]);
        }
        double *tmp = u;
        u = un;
        un = tmp;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    const double elapsed =
        (double)(t1.tv_sec - t0.tv_sec) + 1e-9 * (double)(t1.tv_nsec - t0.tv_nsec);
    fprintf(stderr, "heat1d: nx=%ld dt=%.3e steps=%ld threads=%d time=%.3fs\n", p.nx, dt, steps,
            threads, elapsed);

    int rc = write_csv(p.out, u, p.nx) == 0 ? RC_OK : RC_USAGE;

    free(u);
    free(un);
    return rc;
}
