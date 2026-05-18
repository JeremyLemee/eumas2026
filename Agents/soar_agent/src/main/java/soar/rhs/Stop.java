package soar.rhs;

import org.eclipse.rdf4j.model.ValueFactory;
import org.eclipse.rdf4j.model.impl.SimpleValueFactory;
import org.jsoar.kernel.Agent;
import org.jsoar.kernel.rhs.functions.RhsFunctionContext;
import org.jsoar.kernel.rhs.functions.RhsFunctionException;
import org.jsoar.kernel.rhs.functions.RhsFunctionHandler;
import org.jsoar.kernel.symbols.Symbol;

import java.util.List;

public class Stop implements RhsFunctionHandler {

    private Agent agent = null;
    private final ValueFactory rdf = SimpleValueFactory.getInstance();

    public void setAgent(Agent agent) {
        this.agent = agent;
        this.agent.getRhsFunctions().registerHandler(this);
    }

    @Override
    public String getName() {
        return "stop";
    }

    @Override
    public int getMinArguments() {
        return 0;
    }

    @Override
    public int getMaxArguments() {
        return 0;
    }

    @Override
    public boolean mayBeStandalone() {
        return true;
    }

    @Override
    public boolean mayBeValue() {
        return false;
    }

    @Override
    public Symbol execute(RhsFunctionContext rhsFunctionContext, List<Symbol> list) throws RhsFunctionException {
        System.exit(0);
        return null;
    }
}
