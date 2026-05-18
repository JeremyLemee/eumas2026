package soar.rhs;

import org.eclipse.rdf4j.model.ValueFactory;
import org.eclipse.rdf4j.model.impl.SimpleValueFactory;
import org.jsoar.kernel.Agent;
import org.jsoar.kernel.rhs.functions.RhsFunctionContext;
import org.jsoar.kernel.rhs.functions.RhsFunctionException;
import org.jsoar.kernel.rhs.functions.RhsFunctionHandler;
import org.jsoar.kernel.symbols.Symbol;

import java.util.List;

public class Wait implements RhsFunctionHandler {

    private Agent agent = null;
    private final ValueFactory rdf = SimpleValueFactory.getInstance();

    public void setAgent(Agent agent) {
        this.agent = agent;
        this.agent.getRhsFunctions().registerHandler(this);
    }

    @Override
    public String getName() {
        return "wait";
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
        return false;
    }

    @Override
    public Symbol execute(RhsFunctionContext rhsFunctionContext, List<Symbol> list) throws RhsFunctionException {
        Symbol s = list.get(0);
        try {
            Thread.sleep(s.asInteger().getValue());
        } catch (InterruptedException e) {
            throw new RuntimeException(e);
        }
        return null;
    }
}
