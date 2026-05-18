package soar.rhs;

import org.jsoar.kernel.rhs.functions.RhsFunctionContext;
import org.jsoar.kernel.rhs.functions.RhsFunctionException;
import org.jsoar.kernel.rhs.functions.RhsFunctionHandler;
import org.jsoar.kernel.symbols.*;

import java.util.List;

public class  PrintActionHandler implements RhsFunctionHandler {
    @Override
    public String getName() {
        return "print-action";
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
    public Symbol execute(RhsFunctionContext context, List<Symbol> arguments) throws RhsFunctionException {
        //System.out.println("execute print action");
        StringBuilder str = new StringBuilder();
        for (Symbol s: arguments){
            str.append(s.toString());
        }
        System.out.println(str);
        return null;
    }
}
