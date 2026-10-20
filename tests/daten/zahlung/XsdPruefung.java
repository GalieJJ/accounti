// Prüft XML-Dateien gegen ein XML-Schema (XSD 1.0) mit javax.xml.validation.
//
//   java tests/daten/zahlung/XsdPruefung.java schema.xsd datei1.xml [datei2.xml …]
//
// Läuft im Quelltextmodus von Java 11+ (kein Kompilieren nötig). Je Datei eine Zeile
// "<datei>: gueltig" oder die Fehler mit Zeile und Spalte; Exit-Code 1, sobald eine
// Datei ungültig ist. DTDs und externe Entities sind abgeschaltet.

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.xml.sax.ErrorHandler;
import org.xml.sax.SAXParseException;

public class XsdPruefung {
    public static void main(String[] args) throws Exception {
        SchemaFactory fabrik = SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);
        fabrik.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        fabrik.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        Schema schema = fabrik.newSchema(new File(args[0]));
        boolean alleGueltig = true;
        for (int i = 1; i < args.length; i++) {
            Validator pruefer = schema.newValidator();
            pruefer.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            pruefer.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            List<String> fehler = new ArrayList<>();
            pruefer.setErrorHandler(new ErrorHandler() {
                public void warning(SAXParseException e) {}
                public void error(SAXParseException e) { fehler.add(text(e)); }
                public void fatalError(SAXParseException e) { fehler.add(text(e)); }
            });
            try {
                pruefer.validate(new StreamSource(new File(args[i])));
            } catch (SAXParseException e) {
                // nach fatalError bereits erfasst
            }
            String name = new File(args[i]).getName();
            if (fehler.isEmpty()) {
                System.out.println(name + ": gueltig");
            } else {
                alleGueltig = false;
                for (String f : fehler) {
                    System.out.println(name + ": " + f);
                }
            }
        }
        System.exit(alleGueltig ? 0 : 1);
    }

    private static String text(SAXParseException e) {
        return "Zeile " + e.getLineNumber() + ", Spalte " + e.getColumnNumber() + ": "
            + e.getMessage();
    }
}
