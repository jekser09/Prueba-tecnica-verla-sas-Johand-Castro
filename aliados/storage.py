"""
Almacenamiento personalizado de archivos estáticos para el proyecto aliados.

Extiende ManifestStaticFilesStorage de Django para integrar minificación nativa
en Python de hojas de estilo (.css) mediante rcssmin y scripts (.js) mediante
rjsmin durante la ejecución de collectstatic, previo al cálculo del hash MD5
y a la generación del manifiesto staticfiles.json.
"""

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage
from django.core.files.base import ContentFile
import rcssmin
import rjsmin


class MinifiedManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """
    Motor de almacenamiento que minifica activos CSS y JS y los serializa
    con hash MD5 de contenido para cache-busting inmutable.
    """

    # Evita errores fatales en entornos de prueba cuando aún no se ha ejecutado collectstatic.
    manifest_strict = False

    def post_process(self, paths, dry_run=False, **options):
        """
        Intercepta el posprocesamiento de collectstatic para minificar archivos
        .js y .css antes de que la clase base calcule el hash MD5 y reescriba
        las referencias en el manifiesto.
        """
        # Si es una ejecución en seco (dry_run), no se modifican archivos en disco.
        if not dry_run:
            # Creamos una copia superficial del diccionario de rutas para apuntar
            # los archivos minificados hacia este almacenamiento destino (self).
            paths = dict(paths)

            for name in list(paths.keys()):
                # Normalizamos el nombre a minúsculas para evaluar su extensión.
                lower_name = name.lower()

                # Omitimos archivos que ya se encuentran pre-minificados (.min.js / .min.css).
                if lower_name.endswith((".min.js", ".min.css")):
                    continue

                # Procesamos únicamente archivos JavaScript (.js) y hojas de estilo (.css)
                # que existan efectivamente en el directorio de salida (STATIC_ROOT).
                if lower_name.endswith((".js", ".css")) and self.exists(name):
                    # Leemos el contenido original codificado en UTF-8 desde STATIC_ROOT.
                    with self.open(name, "rb") as original_file:
                        content = original_file.read().decode("utf-8")

                    # Aplicamos el minificador correspondiente según el tipo de activo.
                    if lower_name.endswith(".js"):
                        minified = rjsmin.jsmin(content)
                    else:
                        minified = rcssmin.cssmin(content)

                    # Eliminamos la versión sin minificar previamente copiada en STATIC_ROOT.
                    self.delete(name)

                    # Guardamos la versión minificada en la misma ruta relativa dentro de STATIC_ROOT.
                    self.save(name, ContentFile(minified.encode("utf-8")))

                    # Actualizamos la referencia en paths para que super().post_process()
                    # lea el archivo ya minificado desde este storage al generar el hash MD5.
                    paths[name] = (self, name)

        # Delegamos a ManifestStaticFilesStorage la generación de nombres con hash MD5,
        # el ajuste de referencias url(...) en CSS y la escritura de staticfiles.json.
        yield from super().post_process(paths, dry_run=dry_run, **options)

    def stored_name(self, name):
        """
        Resuelve el nombre del archivo con hash MD5 desde el manifiesto; si el archivo
        aún no ha sido recolectado (por ejemplo durante pruebas unitarias), retorna la
        ruta limpia original como respaldo seguro.
        """
        try:
            return super().stored_name(name)
        except ValueError:
            return self.clean_name(name)
