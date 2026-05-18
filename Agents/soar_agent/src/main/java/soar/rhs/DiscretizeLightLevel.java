package soar.rhs;

import org.jsoar.kernel.Agent;
import org.jsoar.kernel.rhs.functions.RhsFunctionContext;
import org.jsoar.kernel.rhs.functions.RhsFunctionException;
import org.jsoar.kernel.rhs.functions.RhsFunctionHandler;
import org.jsoar.kernel.symbols.Symbol;

import java.util.List;

public class DiscretizeLightLevel implements RhsFunctionHandler {

    private final Agent agent;

    public DiscretizeLightLevel(Agent agent) {
        if (agent == null) {
            throw new IllegalArgumentException("agent must not be null");
        }
        this.agent = agent;
    }

    @Override
    public String getName() {
        return "discretize-light-level";
    }

    @Override
    public int getMinArguments() {
        return 1;
    }

    @Override
    public int getMaxArguments() {
        return 1;
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
        final double value = parseNumeric(arguments.get(0));
        final int bucket = discretize(value);
        return this.agent.getSymbols().createInteger(bucket);
    }

    private static double parseNumeric(Symbol symbol) throws RhsFunctionException {
        if (symbol.asInteger() != null) {
            return symbol.asInteger().getValue();
        }

        if (symbol.asDouble() != null) {
            return symbol.asDouble().getValue();
        }

        final String text = symbol.toString().replace("|", "").trim();

        try {
            return Double.parseDouble(text);
        } catch (NumberFormatException e) {
            throw new RhsFunctionException(
                    "discretize-light-level expected a numeric argument, got: " + symbol,
                    e
            );
        }
    }

    private static int discretize(double value) {
        if (value < 50.0) {
            return 0;
        }

        if (value < 200.0) {
            return 1;
        }

        if (value < 700.0) {
            return 2;
        }

        return 3;
    }
}