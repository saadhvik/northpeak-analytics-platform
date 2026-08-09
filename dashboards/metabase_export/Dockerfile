# Metabase's official image is Alpine (musl libc), but the community DuckDB
# driver bundles a native JDBC library built against glibc. Installing
# libstdc++ + gcompat (Alpine's glibc-compat shim) fixes the loader errors,
# but the mixed musl-JVM / glibc-native-lib combination is still unstable:
# DuckDB's C++ exception unwinding breaks across that ABI boundary, so every
# call into the native engine fails with an uninformative
# "Invalid Error: No error information" (reproduced directly against the JNI
# layer with jjs, independent of Metabase/Clojure — see README.md).
#
# Fix: run Metabase on a genuine glibc base instead of patching Alpine. Grab
# the app jar from the official image and run it under a Debian-based JRE.
FROM metabase/metabase:v0.50.8 AS metabase-app

FROM eclipse-temurin:11-jre-jammy
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
# run_metabase.sh drops privileges with `su metabase -s /bin/sh -c "exec java …"`,
# and Debian's su resets PATH to a minimal default that excludes the temurin
# JDK dir — so java must be reachable from a standard PATH location too.
RUN ln -s "$JAVA_HOME/bin/java" /usr/local/bin/java
COPY --from=metabase-app /app /app
WORKDIR /app
EXPOSE 3000
ENTRYPOINT ["/app/run_metabase.sh"]
