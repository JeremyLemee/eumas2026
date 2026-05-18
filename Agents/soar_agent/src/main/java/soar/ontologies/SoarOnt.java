package soar.ontologies;

import org.eclipse.rdf4j.model.IRI;
import org.eclipse.rdf4j.model.ValueFactory;
import org.eclipse.rdf4j.model.impl.SimpleValueFactory;

public class SoarOnt {

    private static final ValueFactory rdf = SimpleValueFactory.getInstance();

    public static IRI soar_ability = rdf.createIRI("http://example.org/soar#soar_ability");

    public static IRI soar_light_processing = rdf.createIRI("http://example.org/soar#soar_light_processing");


    public static IRI first = rdf.createIRI("http://example.org/soar#first");

    public static IRI hasIdentifier = rdf.createIRI("http://example.org/soar#hasIdentifier");

    public static IRI hasAttribute= rdf.createIRI("http://example.org/soar#hasAttribute");

    public static IRI hasValue = rdf.createIRI("http://example.org/soar#hasValue");

    public static IRI hasLiteral = rdf.createIRI("http://example.org/soar#hasLiteral");

    public static IRI hasInputLink = rdf.createIRI("http://example.org/soar#hasInputLink");

    public static IRI hasRelation = rdf.createIRI("http://example.org/soar#hasRelation");

    public static IRI done = rdf.createIRI("http://example.org/soar#done");

    public static IRI reason = rdf.createIRI("http://example.org/soar#reason");

    public static IRI eventId = rdf.createIRI("http://example.org/soar#eventId");

    public static IRI goalZ1 = rdf.createIRI("http://example.org/soar#goalZ1");

    public static IRI goalZ2 = rdf.createIRI("http://example.org/soar#goalZ2");

    public static IRI AddWME = rdf.createIRI("http://example.org/soar#AddWME");

    public static IRI WMETurn = rdf.createIRI("http://example.org/soar#WMETurn");

    public static IRI predicate = rdf.createIRI("http://example.org/soar#predicate");

}
