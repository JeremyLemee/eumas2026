// KgValue.java
package soar.rhs;

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
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.Optional;

public class KgValue implements RhsFunctionHandler {
    private static final String HMAS_HAS_STATE = "https://purl.org/hmas/hasState";

    private Agent agent;

    public KgValue(Agent agent) {
        this.agent = agent;
    }

    @Override
    public String getName() {
        return "kg-value";
    }

    @Override
    public int getMinArguments() {
        return 2;
    }

    @Override
    public int getMaxArguments() {
        return 2;
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
        String propertyLocalName = clean(arguments.get(1));

        Model model = loadKg(kgUrl);

        Resource stateNode = findStateNode(model)
                .orElseThrow(() -> new RhsFunctionException("No hmas:hasState node found in KG"));

        Value value = findObjectByLocalName(model, stateNode, propertyLocalName)
                .orElseThrow(() -> new RhsFunctionException(
                        "No state property found with local name " + propertyLocalName
                ));

        return toSymbol(value);
    }

    private Model loadKg(String url) throws RhsFunctionException {
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Accept", "text/turtle, application/x-turtle, text/plain, */*")
                    .GET()
                    .build();

            HttpResponse<String> response =
                    HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());

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

    private Optional<Resource> findStateNode(Model model) {
        for (Statement st : model) {
            if (st.getPredicate().stringValue().equals(HMAS_HAS_STATE)
                    && st.getObject() instanceof Resource resource) {
                return Optional.of(resource);
            }
        }
        return Optional.empty();
    }

    private Optional<Value> findObjectByLocalName(Model model, Resource subject, String localName) {
        for (Statement st : model.filter(subject, null, null)) {
            if (st.getPredicate().getLocalName().equals(localName)) {
                return Optional.of(st.getObject());
            }
        }
        return Optional.empty();
    }

    private Symbol toSymbol(Value value) {
        if (value instanceof Literal literal) {
            String label = literal.getLabel();

            if ("true".equalsIgnoreCase(label) || "false".equalsIgnoreCase(label)) {
                return agent.getSymbols().createString(Boolean.toString(Boolean.parseBoolean(label)));
            }

            if (label.matches("-?\\d+")) {
                try {
                    return agent.getSymbols().createInteger(Long.parseLong(label));
                } catch (NumberFormatException ignored) {
                    return agent.getSymbols().createString(label);
                }
            }

            if (label.matches("-?\\d+(\\.\\d+)?([eE][+-]?\\d+)?")) {
                try {
                    return agent.getSymbols().createDouble(Double.parseDouble(label));
                } catch (NumberFormatException ignored) {
                    return agent.getSymbols().createString(label);
                }
            }

            return agent.getSymbols().createString(label);
        }

        return agent.getSymbols().createString(value.stringValue());
    }

    private static String clean(Symbol symbol) {
        return symbol.toString().replace("|", "").trim();
    }
}