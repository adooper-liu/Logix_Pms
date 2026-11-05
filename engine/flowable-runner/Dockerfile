FROM maven:3.9.9-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY pom.xml .
RUN mvn -B dependency:go-offline
COPY src ./src
RUN mvn -B -Dmaven.test.skip=true package

FROM eclipse-temurin:21-jre
ARG BUILD_REVISION=unknown
ENV BUILD_REVISION=$BUILD_REVISION
WORKDIR /app
RUN useradd --system --uid 10001 runner
COPY --from=build /workspace/target/flowable-poc-0.0.1.jar app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-Duser.timezone=UTC", "-jar", "/app/app.jar"]
