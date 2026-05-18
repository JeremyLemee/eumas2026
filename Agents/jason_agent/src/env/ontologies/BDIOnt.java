package ontologies;

import org.eclipse.rdf4j.model.IRI;
import org.eclipse.rdf4j.model.ValueFactory;
import org.eclipse.rdf4j.model.impl.SimpleValueFactory;

public class BDIOnt {

    private static final ValueFactory rdf = SimpleValueFactory.getInstance();
    private static final String BDI_NAMESPACE = "http://localhost:8082/ontologies/bdi#";

    public static IRI hasPredicate = rdf.createIRI(BDI_NAMESPACE + "hasPredicate");

    public static IRI hasValues = rdf.createIRI(BDI_NAMESPACE + "hasValues");

    public static IRI hasStatement = rdf.createIRI(BDI_NAMESPACE + "hasStatement");

    public static IRI predicate_ability = rdf.createIRI(BDI_NAMESPACE + "predicate_ability");

    public static IRI set_goal = rdf.createIRI(BDI_NAMESPACE + "set_goal");

    public static IRI set_env = rdf.createIRI(BDI_NAMESPACE + "set_env");

    public static IRI disable_z1_blinds = rdf.createIRI(BDI_NAMESPACE + "disable_z1_blinds");

    public static IRI disable_z2_blinds = rdf.createIRI(BDI_NAMESPACE + "disable_z2_blinds");

}
