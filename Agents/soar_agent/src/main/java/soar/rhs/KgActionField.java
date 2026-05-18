package soar.rhs;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import org.eclipse.rdf4j.model.Literal;
import org.eclipse.rdf4j.model.Model;
import org.eclipse.rdf4j.model.Resource;
import org.eclipse.rdf4j.model.Statement;
import org.eclipse.rdf4j.model.Value;
import org.eclipse.rdf4j.rio.RDFFormat;
import org.eclipse.rdf4j.rio.Rio;
import org.jsoar.kernel.Agent;
import org.jsoar.kernel.rhs.functions.RhsFunctionContext;
import org.jsoar.kernel.rhs.functions.RhsFunctionException;
import org.jsoar.kernel.rhs.functions.RhsFunctionHandler;
import org.jsoar.kernel.symbols.Symbol;

import java.io.StringReader;
import java.lang.reflect.Type;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class KgActionField implements RhsFunctionHandler {
    private static final String RDF_TYPE =
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";

    private static final String HMAS_ACTION_SPECIFICATION =
            "https://purl.org/hmas/ActionSpecification";

    private static final String HMAS_HAS_OPERATION =
            "https://purl.org/hmas/hasOperation";

    private static final String SCHEMA_NAME =
            "http://schema.org/name";

    private static final String HTTP_BODY =
            "http://www.w3.org/2011/http#body";

    private static final String HTTP_METHOD_NAME =
            "http://www.w3.org/2011/http#methodName";

    private static final String HTTP_REQUEST_URI =
            "http://www.w3.org/2011/http#requestURI";

    private final Agent agent;
    private final HttpClient httpClient;
    private final Gson gson;

    public KgActionField(Agent agent) {
        this.agent = agent;
        this.httpClient = HttpClient.newHttpClient();
        this.gson = new Gson();
    }

    @Override
    public String getName() {
        return "kg-action-field";
    }

    @Override
    public int getMinArguments() {
        return 4;
    }

    @Override
    public int getMaxArguments() {
        return 4;
    }

    @Override
    public boolean mayBeStandalone() {
        return false;
    }

    @Override
    public boolean mayBeValue() {
        return true;
    }

    @Override
    public Symbol execute(RhsFunctionContext context, List<Symbol> arguments) throws RhsFunctionException {
        String kgUrl = clean(arguments.get(0));
        String requestedDevice = clean(arguments.get(1));
        boolean requestedActivate = parseBoolean(arguments.get(2));
        String requestedField = clean(arguments.get(3));

        Model model = loadKg(kgUrl);

        Optional<ActionSpec> maybeAction = findAction(model, requestedDevice, requestedActivate);

        if (maybeAction.isEmpty()) {
            if ("available".equals(requestedField)) {
                return stringSymbol("false");
            }

            return stringSymbol("none");
        }

        ActionSpec action = maybeAction.get();

        String value = switch (requestedField) {
            case "available" -> "true";
            case "name" -> action.name();
            case "method" -> action.method();
            case "url" -> action.url();
            case "body" -> action.body();
            case "pre-attribute" -> action.preAttribute();
            case "pre-value" -> action.preValue();
            case "post-attribute" -> action.postAttribute();
            case "post-value" -> action.postValue();
            case "zone" -> action.zone();
            case "effect" -> action.effect();
            case "control" -> action.control();
            default -> throw new RhsFunctionException("Unknown kg-action-field: " + requestedField);
        };

        return stringSymbol(value);
    }

    private Model loadKg(String url) throws RhsFunctionException {
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Accept", "text/turtle, application/x-turtle, text/plain, */*")
                    .GET()
                    .build();

            HttpResponse<String> response =
                    httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new RhsFunctionException(
                        "KG request failed with status " + response.statusCode() + " for " + url
                );
            }

            return Rio.parse(new StringReader(response.body()), "", RDFFormat.TURTLE);
        } catch (RhsFunctionException e) {
            throw e;
        } catch (Exception e) {
            throw new RhsFunctionException("Could not load KG from " + url + ": " + e.getMessage(), e);
        }
    }

    private Optional<ActionSpec> findAction(Model model, String requestedDevice, boolean requestedActivate)
            throws RhsFunctionException {
        List<ActionSpec> candidates = new ArrayList<>();

        for (Statement statement : model) {
            if (!statement.getPredicate().stringValue().equals(RDF_TYPE)) {
                continue;
            }

            if (!statement.getObject().stringValue().equals(HMAS_ACTION_SPECIFICATION)) {
                continue;
            }

            if (!(statement.getSubject() instanceof Resource actionNode)) {
                continue;
            }

            Optional<Resource> operationNode = objectResource(model, actionNode, HMAS_HAS_OPERATION);

            if (operationNode.isEmpty()) {
                continue;
            }

            String body = objectString(model, operationNode.get(), HTTP_BODY).orElse("");

            Optional<OperationCommand> maybeCommand = parseOperationCommand(body);

            if (maybeCommand.isEmpty()) {
                continue;
            }

            OperationCommand command = maybeCommand.get();

            if (!requestedDevice.equalsIgnoreCase(command.device())) {
                continue;
            }

            if (requestedActivate != command.activate()) {
                continue;
            }

            String normalizedDevice = command.device().trim().toUpperCase();

            String name = objectString(model, actionNode, SCHEMA_NAME)
                    .orElse(defaultName(normalizedDevice, command.activate()));

            String method = objectString(model, operationNode.get(), HTTP_METHOD_NAME)
                    .orElse("POST");

            String url = objectString(model, operationNode.get(), HTTP_REQUEST_URI)
                    .orElseThrow(() -> new RhsFunctionException("Action " + name + " has no http:requestURI"));

            // The light-processing Soar agent is limited to operational actions only.
            // Administrative enable/disable affordances exposed via /control must not be selected.
            if (!url.trim().toLowerCase().endsWith("/action")) {
                continue;
            }

            String zone = zoneFromDevice(normalizedDevice);
            String control = controlFromDevice(normalizedDevice);
            String effect = effectFromActivation(command.activate());
            String controlledAttribute = controlledAttributeFromDevice(normalizedDevice);

            if ("unknown".equals(zone)) {
                throw new RhsFunctionException("Cannot infer zone from device: " + normalizedDevice);
            }

            if ("unknown".equals(control)) {
                throw new RhsFunctionException("Cannot infer control from device: " + normalizedDevice);
            }

            if ("unknown".equals(controlledAttribute)) {
                throw new RhsFunctionException("Cannot infer controlled attribute from device: " + normalizedDevice);
            }

            String preValue = Boolean.toString(!command.activate());
            String postValue = Boolean.toString(command.activate());

            candidates.add(new ActionSpec(
                    name,
                    method,
                    url,
                    body,
                    controlledAttribute,
                    preValue,
                    controlledAttribute,
                    postValue,
                    zone,
                    effect,
                    control
            ));
        }

        return candidates.stream()
                .max(Comparator
                        .comparingInt(this::actionPreferenceScore)
                        .thenComparing(ActionSpec::url)
                        .thenComparing(ActionSpec::body)
                        .thenComparing(ActionSpec::name));
    }

    private Optional<OperationCommand> parseOperationCommand(String body) throws RhsFunctionException {
        String trimmed = body == null ? "" : body.trim();

        if (trimmed.isEmpty()) {
            return Optional.empty();
        }

        try {
            Type type = new TypeToken<LinkedHashMap<String, Object>>() {
            }.getType();

            Map<String, Object> map = gson.fromJson(trimmed, type);

            if (map == null || map.isEmpty()) {
                return Optional.empty();
            }

            Optional<OperationCommand> modern = parseModernDeviceActivateCommand(map);
            if (modern.isPresent()) {
                return modern;
            }

            Optional<OperationCommand> legacy = parseLegacyDeviceBooleanCommand(map);
            if (legacy.isPresent()) {
                return legacy;
            }

            return Optional.empty();
        } catch (Exception e) {
            throw new RhsFunctionException("Could not parse action body as JSON: " + body, e);
        }
    }

    private Optional<OperationCommand> parseModernDeviceActivateCommand(Map<String, Object> map) {
        Object rawDevice = map.get("device");
        Object rawActivate = map.get("activate");

        if (!(rawDevice instanceof String device)) {
            return Optional.empty();
        }

        if (!(rawActivate instanceof Boolean activate)) {
            return Optional.empty();
        }

        String normalizedDevice = device.trim().toUpperCase();

        if (!isKnownDevice(normalizedDevice)) {
            return Optional.empty();
        }

        return Optional.of(new OperationCommand(normalizedDevice, activate));
    }

    private Optional<OperationCommand> parseLegacyDeviceBooleanCommand(Map<String, Object> map) {
        if (map.size() != 1) {
            return Optional.empty();
        }

        Map.Entry<String, Object> entry = map.entrySet().iterator().next();

        String device = entry.getKey().trim().toUpperCase();

        if (!isKnownDevice(device)) {
            return Optional.empty();
        }

        Object rawActivate = entry.getValue();

        if (!(rawActivate instanceof Boolean activate)) {
            return Optional.empty();
        }

        return Optional.of(new OperationCommand(device, activate));
    }

    private boolean isKnownDevice(String device) {
        return switch (device.toUpperCase()) {
            case "L1", "L2", "B1", "B2" -> true;
            default -> false;
        };
    }

    private String defaultName(String device, boolean activate) {
        return (activate ? "Enable " : "Disable ") + device.toUpperCase();
    }

    private String zoneFromDevice(String device) {
        return switch (device.toUpperCase()) {
            case "L1", "B1" -> "Z1";
            case "L2", "B2" -> "Z2";
            default -> "unknown";
        };
    }

    private String controlFromDevice(String device) {
        return switch (device.toUpperCase()) {
            case "L1", "L2" -> "light";
            case "B1", "B2" -> "blinds";
            default -> "unknown";
        };
    }

    private String controlledAttributeFromDevice(String device) {
        return switch (device.toUpperCase()) {
            case "L1" -> "z1light";
            case "L2" -> "z2light";
            case "B1" -> "z1blinds";
            case "B2" -> "z2blinds";
            default -> "unknown";
        };
    }

    private String effectFromActivation(boolean activate) {
        return activate ? "increase" : "decrease";
    }

    private int actionPreferenceScore(ActionSpec action) {
        int score = 0;
        String normalizedUrl = action.url().trim().toLowerCase();
        String normalizedBody = action.body().trim();

        if (normalizedUrl.endsWith("/action")) {
            score += 100;
        }

        if (normalizedUrl.endsWith("/control")) {
            score -= 100;
        }

        if (normalizedBody.startsWith("{\"device\"")) {
            score -= 10;
        } else {
            score += 10;
        }

        return score;
    }

    private Optional<Resource> objectResource(Model model, Resource subject, String predicateUri) {
        return objectValue(model, subject, predicateUri)
                .filter(value -> value instanceof Resource)
                .map(value -> (Resource) value);
    }

    private Optional<String> objectString(Model model, Resource subject, String predicateUri) {
        return objectValue(model, subject, predicateUri).map(this::normalizeRdfValue);
    }

    private Optional<Value> objectValue(Model model, Resource subject, String predicateUri) {
        for (Statement statement : model.filter(subject, null, null)) {
            if (statement.getPredicate().stringValue().equals(predicateUri)) {
                return Optional.of(statement.getObject());
            }
        }

        return Optional.empty();
    }

    private String normalizeRdfValue(Value value) {
        if (value instanceof Literal literal) {
            return literal.getLabel();
        }

        return value.stringValue();
    }

    private boolean parseBoolean(Symbol symbol) throws RhsFunctionException {
        String text = clean(symbol);

        if ("true".equalsIgnoreCase(text)) {
            return true;
        }

        if ("false".equalsIgnoreCase(text)) {
            return false;
        }

        throw new RhsFunctionException("Expected boolean symbol, got: " + symbol);
    }

    private Symbol stringSymbol(String value) {
        return agent.getSymbols().createString(value);
    }

    private static String clean(Symbol symbol) {
        return symbol.toString().replace("|", "").trim();
    }

    private record OperationCommand(String device, boolean activate) {
    }

    private record ActionSpec(
            String name,
            String method,
            String url,
            String body,
            String preAttribute,
            String preValue,
            String postAttribute,
            String postValue,
            String zone,
            String effect,
            String control
    ) {
    }
}
